"""Make a run's calls: resumable, concurrent, and safe to split between people and machines.

A trial is done once it has a valid attempt: completed, with no harness failure. The next collect
retries every other trial, up to runs.MAX_CALL_ATTEMPTS failed attempts each. A failed attempt is an
error (a timeout, a CLI failure, output that is not JSON) or a harness failure: another model served,
not exactly one fresh turn, error events, a missing or reused session ID, or no output token count.
Usage-limit stops and Ctrl-C do not use up an attempt. A trial that fails every attempt is left out
of the analysis. A valid call is never rerun, whatever its outcome: a wrong number, a gave-up, a
cut-off, or something the model did itself, such as trying a tool, which is flagged and scored like
any other answer. A model stops for the session at its usage limit, a fatal error (not logged in,
model unavailable), or three failed calls in a row; its calls in flight still finish and are saved,
and the other models keep going.

Each model gets its own lane, with its own Limits, so one subscription's pace never holds back the
other's. Calls run on threads: each one waits on a CLI subprocess, so there is no Python work to
spread across processes.
"""

from __future__ import annotations

import hashlib
import sys
import threading
import time
from collections import Counter, deque
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass, field

from experiment.clients import Client, ClientError, Completion, FatalClientError, UsageLimitError, stop_all
from experiment.runs import Run, Trial, counted, git_state, left_out, now, read_attempts, write_attempt
from experiment.scoring import hit_length_limit, score

MAX_FAILURES_IN_A_ROW = 3


@dataclass(frozen=True)
class Limits:
    """How hard collect pushes one model's subscription.

    Neither CLI's subscription publishes a per-minute or concurrency cap: both meter usage in 5-hour
    and weekly windows, which parallel calls only spend sooner. Both CLIs also retry a 429 themselves
    before failing, and the failure then stops the model like a usage limit. So these defaults keep
    bursts down; they do not enforce a known quota.
    """

    workers: int = 3  # calls in flight at once
    calls_per_minute: float = 6  # call starts are spaced 60 / calls_per_minute seconds apart

    def __post_init__(self):
        if self.workers < 1 or self.calls_per_minute <= 0:
            raise ValueError("workers must be at least 1 and calls_per_minute must be positive")


@dataclass
class _Lane:
    """One model's calls still to start, how many are in flight, and when pacing allows the next."""

    client: Client
    limits: Limits
    queue: deque[Trial] = field(default_factory=deque)
    in_flight: int = 0
    next_start: float = 0.0  # time.monotonic()

    def seconds_to_start(self, clock: float) -> float | None:
        """0 if a call can start now; None if none can start until a call finishes (or none is left)."""
        if not self.queue or self.in_flight >= self.limits.workers:
            return None
        return max(0.0, self.next_start - clock)

    def start(self, clock: float) -> Trial:
        self.in_flight += 1
        self.next_start = clock + 60 / self.limits.calls_per_minute
        return self.queue.popleft()


@dataclass
class Summary:
    calls: int = 0
    outcomes: Counter = field(default_factory=Counter)  # answer statuses, plus "error" and "harness failure"
    stopped: dict[str, str] = field(default_factory=dict)  # model -> why it stopped
    interrupted: bool = False


def in_shard(trial: Trial, shard: tuple[int, int] | None) -> bool:
    """Shard k of n: a fixed share of trials, the same whoever runs it and whatever else is filtered."""
    if shard is None:
        return True
    k, n = shard
    return int(hashlib.sha256(trial.trial_id.encode()).hexdigest(), 16) % n == k - 1


class SessionIds:
    """Every session ID the run has seen, so a call that reports one again is caught as a harness failure."""

    def __init__(self, attempts: list[dict]):
        self._seen = {a["session_id"] for a in attempts if a.get("session_id")}
        self._lock = threading.Lock()  # calls finish on several threads

    def is_new(self, session_id: str) -> bool:
        """Record session_id; False if the run had already seen it."""
        with self._lock:
            new = session_id not in self._seen
            self._seen.add(session_id)
            return new


def pending(run: Run, models: list[str] | None = None, shard: tuple[int, int] | None = None) -> list[Trial]:
    """The selected trials with no valid attempt and attempts left."""
    attempts = read_attempts(run)
    done = counted(attempts).keys() | left_out(attempts)
    return [t for t in run.trials if t.trial_id not in done and (not models or t.model in models) and in_shard(t, shard)]


def harness_failures(completion: Completion, sessions: SessionIds) -> list[str]:
    """The client's own harness checks, plus the ones both CLIs share: a new session ID and an output token count."""
    failures = list(completion.harness_failures)
    if not completion.session_id:
        failures.append("no session id")
    elif not sessions.is_new(completion.session_id):
        failures.append(f"session {completion.session_id} was already used in this run")
    if completion.usage.get("output_tokens") is None:
        failures.append("no output token count")
    return failures


def call(run: Run, trial: Trial, client: Client, session: dict, sessions: SessionIds) -> dict:
    """One call; its attempt file is written before this returns, whatever happened."""
    spec = client.spec
    prompt = run.prompt(trial)
    record = {
        **asdict(trial), "provider": spec.provider, "model_id": spec.model, "effort": spec.effort,
        **session, "client_version": client.version,
        "prompt_sha256": hashlib.sha256((prompt.system + "\0" + prompt.user).encode()).hexdigest(),
        "started_at": now(),
    }
    started = time.monotonic()
    try:
        completion = client.complete(prompt, run.config.timeout_seconds)
    except ClientError as error:
        record.update(status="error", error_type=type(error).__name__, error=str(error), eligible=False)
    else:
        failures = harness_failures(completion, sessions)
        record.update(
            status="completed", error=None, response=completion.text, usage=completion.usage,
            served_model=completion.served_model, stop_reason=completion.stop_reason, session_id=completion.session_id,
            harness_failures=failures, model_flags=completion.model_flags, eligible=not failures, raw=completion.raw,
        )
    record.update(finished_at=now(), elapsed_s=round(time.monotonic() - started, 1))
    record["file"] = str(write_attempt(run, record).relative_to(run.path))
    return record


def collect(run: Run, clients: dict[str, Client], trials: list[Trial], operator: str, limits: dict[str, Limits]) -> Summary:
    """Make the trials' calls, each model in schedule order within its own Limits."""
    session = {"operator": operator, **git_state()}
    sessions = SessionIds(read_attempts(run))
    summary = Summary()
    lanes = {model: _Lane(client, limits[model]) for model, client in clients.items()}
    for trial in trials:
        lanes[trial.model].queue.append(trial)
    streak: Counter = Counter()
    running: dict[Future, Trial] = {}
    width = len(str(len(trials)))
    pool = ThreadPoolExecutor(max_workers=sum(lane.limits.workers for lane in lanes.values()))
    try:
        while True:
            clock = time.monotonic()
            for lane in lanes.values():
                if lane.seconds_to_start(clock) == 0:
                    trial = lane.start(clock)
                    running[pool.submit(call, run, trial, lane.client, session, sessions)] = trial
            waits = [s for lane in lanes.values() if (s := lane.seconds_to_start(clock)) is not None]
            if not running and not waits:
                break
            # Wake for the first call to finish, or for the next start pacing allows, whichever is sooner.
            finished, _ = wait(running, timeout=min(waits, default=None), return_when=FIRST_COMPLETED)
            for future in finished:
                trial = running.pop(future)
                lane = lanes[trial.model]
                lane.in_flight -= 1
                summary.calls += 1
                prefix = f"[{summary.calls:>{width}}/{len(trials)}] {trial.world_id} {trial.version:2} {trial.instruction} {trial.model} r{trial.repeat}"
                _report(summary, streak, trial, future.result(), prefix, run.keys[trial.world_id], lane.client.spec.max_output_tokens)
                if trial.model in summary.stopped:
                    lane.queue.clear()
    except KeyboardInterrupt:
        stop_all()
        summary.interrupted = True
        print("\nInterrupted: the calls in flight were stopped and saved as errors; the next collect retries them "
              "without using up an attempt.", file=sys.stderr)
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    return summary


def _report(summary: Summary, streak: Counter, trial: Trial, record: dict, prefix: str, key: dict, max_output_tokens: int) -> None:
    model = trial.model
    if record["status"] == "error" or not record["eligible"]:
        harness = record["status"] == "completed"
        problem = "harness failure: " + "; ".join(record["harness_failures"]) if harness else record["error"]
        summary.outcomes["harness failure" if harness else "error"] += 1
        streak[model] += 1
        print(f"{prefix}  FAILED {problem}", flush=True)
        fatal = record.get("error_type") in (UsageLimitError.__name__, FatalClientError.__name__)
        if (fatal or streak[model] >= MAX_FAILURES_IN_A_ROW) and model not in summary.stopped:
            summary.stopped[model] = problem if fatal else f"{MAX_FAILURES_IN_A_ROW} failed calls in a row; last: {problem}"
        return
    streak[model] = 0
    usage = record["usage"]
    tokens = f"in {usage.get('input_tokens') or 0:,} out {usage.get('output_tokens') or 0:,}"
    scored = score(record["response"], key, hit_length_limit(usage, record["stop_reason"], max_output_tokens))
    summary.outcomes[scored["status"]] += 1
    flagged = f"  flagged: {'; '.join(record['model_flags'])}" if record["model_flags"] else ""
    print(f"{prefix}  {scored['status']} ({scored['value']} vs {scored['expected']}){flagged}  {record['elapsed_s']:.0f}s  {tokens}", flush=True)
