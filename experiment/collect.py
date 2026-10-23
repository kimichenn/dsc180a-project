"""Make a run's calls: resumable, concurrent, and safe to split between people and machines.

A trial is done once it has a completed, eligible attempt. The next collect retries everything
else: errors (timeouts, usage limits, CLI failures) and completed calls that failed the audit (used
a tool, served another model, more than one turn). Wrong answers and gave-ups are never retried.
A model stops for the session at its first audit failure, its usage limit, a fatal error (not
logged in, model unavailable), or three errors in a row; the other models keep going.
"""

from __future__ import annotations

import hashlib
import sys
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass, field

from experiment.clients import Client, ClientError, FatalClientError, UsageLimitError, stop_all
from experiment.runs import Run, Trial, counted, git_state, now, read_attempts, write_attempt
from experiment.scoring import hit_length_limit, score

MAX_ERRORS_IN_A_ROW = 3


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


def collect(run: Run, clients: dict[str, Client], trials: list[Trial], operator: str, workers: int = 1) -> Summary:
    session = {"operator": operator, **git_state()}
    summary = Summary()
    queue = list(trials)
    streak: Counter = Counter()
    running = {}
    width = len(str(len(trials)))
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        while queue or running:
            while len(running) < workers and queue:
                trial = queue.pop(0)
                if trial.model not in summary.stopped:
                    running[pool.submit(call, run, trial, clients[trial.model], session)] = trial
            if not running:
                break
            finished, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in finished:
                trial = running.pop(future)
                record = future.result()
                summary.calls += 1
                prefix = f"[{summary.calls:>{width}}/{len(trials)}] {trial.world_id} {trial.version:2} {trial.instruction} {trial.model} r{trial.repeat}"
                _report(summary, streak, trial, record, prefix, run.keys[trial.world_id], clients[trial.model].spec.max_output_tokens)
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
    scored = score(record["response"], key, trial.version, hit_length_limit(usage, record["stop_reason"], max_output_tokens))
    summary.outcomes[scored["bucket"]] += 1
    print(f"{prefix}  {scored['bucket']} ({scored['value']} vs {scored['expected']})  {record['elapsed_s']:.0f}s  {tokens}", flush=True)
