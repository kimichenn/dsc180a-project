"""Make a run's calls: resumable, concurrent, and safe to split between people and machines.

A trial is done once it has a completed, eligible attempt. The next collect retries everything
else: errors (timeouts, usage limits, CLI failures) and completed calls that failed the audit (used
a tool, served another model, more than one turn). Wrong answers and gave-ups are never retried.
A model stops for the session at its first audit failure, its usage limit, a fatal error (not
logged in, model unavailable), or three errors in a row; its calls in flight still finish and are
saved, and the other models keep going.

Each model gets its own lane, with its own Limits, so one subscription's pace never holds back the
other's. Calls run on threads: each one waits on a CLI subprocess, so there is no Python work to
spread across processes.
"""

from __future__ import annotations

import hashlib
import sys
import time
from collections import Counter, deque
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass, field

from experiment.clients import Client, ClientError, FatalClientError, UsageLimitError, stop_all
from experiment.runs import Run, Trial, counted, git_state, now, read_attempts, write_attempt
from experiment.scoring import hit_length_limit, score

MAX_ERRORS_IN_A_ROW = 3


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
    outcomes: Counter = field(default_factory=Counter)  # answer buckets, plus "error" and "not eligible"
    stopped: dict[str, str] = field(default_factory=dict)  # model -> why it stopped
    interrupted: bool = False


def in_shard(trial: Trial, shard: tuple[int, int] | None) -> bool:
    """Shard k of n: a fixed share of trials, the same whoever runs it and whatever else is filtered."""
    if shard is None:
        return True
    k, n = shard
    return int(hashlib.sha256(trial.trial_id.encode()).hexdigest(), 16) % n == k - 1


def pending(run: Run, models: list[str] | None = None, shard: tuple[int, int] | None = None) -> list[Trial]:
    done = counted(read_attempts(run))
    return [t for t in run.trials if t.trial_id not in done and (not models or t.model in models) and in_shard(t, shard)]


def call(run: Run, trial: Trial, client: Client, session: dict) -> dict:
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
        record.update(
            status="completed", error=None, response=completion.text, usage=completion.usage,
            served_model=completion.served_model, stop_reason=completion.stop_reason,
            audit=completion.audit, eligible=not completion.audit, raw=completion.raw,
        )
    record.update(finished_at=now(), elapsed_s=round(time.monotonic() - started, 1))
    record["file"] = str(write_attempt(run, record).relative_to(run.path))
    return record


def collect(run: Run, clients: dict[str, Client], trials: list[Trial], operator: str, limits: dict[str, Limits]) -> Summary:
    """Make the trials' calls, each model in schedule order within its own Limits."""
    session = {"operator": operator, **git_state()}
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
                    running[pool.submit(call, run, trial, lane.client, session)] = trial
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
        print("\nInterrupted: the calls in flight were stopped and saved as errors; the next collect retries them.", file=sys.stderr)
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    return summary


def _report(summary: Summary, streak: Counter, trial: Trial, record: dict, prefix: str, key: dict, max_output_tokens: int) -> None:
    model = trial.model
    if record["status"] == "error":
        summary.outcomes["error"] += 1
        streak[model] += 1
        print(f"{prefix}  ERROR {record['error']}", flush=True)
        fatal = record["error_type"] in (UsageLimitError.__name__, FatalClientError.__name__)
        if (fatal or streak[model] >= MAX_ERRORS_IN_A_ROW) and model not in summary.stopped:
            summary.stopped[model] = record["error"] if fatal else f"{MAX_ERRORS_IN_A_ROW} errors in a row; last: {record['error']}"
        return
    streak[model] = 0
    usage = record["usage"]
    tokens = f"in {usage.get('input_tokens') or 0:,} out {usage.get('output_tokens') or 0:,}"
    if not record["eligible"]:
        summary.outcomes["not eligible"] += 1
        summary.stopped.setdefault(model, f"{record['file']} failed the audit ({'; '.join(record['audit'])}); inspect it before collecting more")
        print(f"{prefix}  NOT ELIGIBLE: {'; '.join(record['audit'])}  {record['elapsed_s']:.0f}s  {tokens}", flush=True)
        return
    scored = score(record["response"], key, hit_length_limit(usage, record["stop_reason"], max_output_tokens))
    summary.outcomes[scored["bucket"]] += 1
    print(f"{prefix}  {scored['bucket']} ({scored['value']} vs {scored['expected']})  {record['elapsed_s']:.0f}s  {tokens}", flush=True)
