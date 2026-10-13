"""Run trials concurrently, appending every raw response to responses.jsonl.

Runs are resumable: rerunning the same command skips trials that already have a
response, and retries ones that ended in an error.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from conflict_eval.design import Design, Trial
from conflict_eval.models import ModelClient, ModelConfig, is_fatal
from conflict_eval.prompts import INSTRUCTIONS, build_prompt
from conflict_eval.scenarios import FillerPassage

RESPONSES_FILE = "responses.jsonl"
MANIFEST_FILE = "manifest.json"
ATTEMPTS = 3  # on top of the SDKs' own retries
BACKOFF_S = 10


class FatalModelError(RuntimeError):
    """A request error that will repeat on every trial, such as a bad key or unknown model."""


@dataclass
class RunSummary:
    attempted: int
    succeeded: int
    failed: int
    skipped: int


def read_rows(run_dir: Path) -> list[dict]:
    path = Path(run_dir) / RESPONSES_FILE
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_responses(run_dir: Path) -> list[dict]:
    """The latest successful response per trial."""
    latest = {}
    for row in read_rows(run_dir):
        if row.get("error") is None:
            latest[row["trial_id"]] = row
    return list(latest.values())


def run_trials(
    trials: list[Trial],
    clients: dict[str, ModelClient],
    filler: list[FillerPassage],
    run_dir: Path,
    workers: int = 4,
) -> RunSummary:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    done = {row["trial_id"] for row in load_responses(run_dir)}
    pending = [t for t in trials if t.id not in done]
    succeeded = failed = 0

    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        with open(run_dir / RESPONSES_FILE, "a") as out:
            futures = [pool.submit(_execute, t, clients[t.model], filler) for t in pending]
            for count, future in enumerate(as_completed(futures), 1):
                row = future.result()  # raises FatalModelError
                out.write(json.dumps(row) + "\n")
                out.flush()
                if row["error"] is None:
                    succeeded += 1
                else:
                    failed += 1
                    print(f"\n  error on {row['trial_id']}: {row['error']}", file=sys.stderr)
                print(f"\r  {count}/{len(pending)} done, {failed} errors", end="", file=sys.stderr, flush=True)
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
        if pending:
            print(file=sys.stderr)
    return RunSummary(len(pending), succeeded, failed, len(trials) - len(pending))


def _execute(trial: Trial, client: ModelClient, filler: list[FillerPassage]) -> dict:
    condition = trial.condition
    prompt = build_prompt(trial.scenario, condition, filler)
    expected, alternative = trial.scenario.expected_answers(condition.question_type, condition.variant)
    row = {
        **trial.record(),
        **client.config.record(),
        "question": trial.scenario.questions[condition.question_type],
        "expected": list(expected),
        "alternative": list(alternative),
        "system": prompt.system,
        "messages": prompt.messages,
    }
    started = time.monotonic()
    try:
        completion = generate_with_retries(client, prompt)
        row.update(
            response=completion.text,
            finish_reason=completion.finish_reason,
            model_version=completion.model_version,
            usage=completion.usage,
            error=None,
        )
    except FatalModelError:
        raise
    except Exception as error:
        row.update(response=None, error=f"{type(error).__name__}: {error}")
    row.update(
        latency_s=round(time.monotonic() - started, 2),
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    return row


def generate_with_retries(client: ModelClient, prompt):
    for attempt in range(ATTEMPTS):
        try:
            return client.generate(prompt)
        except Exception as error:
            if is_fatal(error):
                raise FatalModelError(f"{client.config.name}: {type(error).__name__}: {error}") from error
            if attempt == ATTEMPTS - 1:
                raise
            time.sleep(BACKOFF_S * 2**attempt)


def write_manifest(
    run_dir: Path,
    design: Design,
    configs: dict[str, ModelConfig],
    scenarios_path: Path,
    scenario_ids: list[str],
    filler: list[FillerPassage],
    seed: int,
) -> dict:
    """Record the run controls. Refuses to mix two different designs in one run directory."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / MANIFEST_FILE
    fixed = _jsonable(
        {
            "design": asdict(design),
            "seed": seed,
            "models": {name: asdict(config) for name, config in configs.items()},
            "scenario_ids": scenario_ids,
        }
    )
    scenarios_sha = hashlib.sha256(Path(scenarios_path).read_bytes()).hexdigest()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if path.exists():
        manifest = json.loads(path.read_text())
        for key, value in fixed.items():
            if manifest[key] != value:
                raise ValueError(f"{run_dir} was started with a different {key}; use a new --out directory")
        if manifest["scenarios_sha256"] != scenarios_sha:
            print(f"warning: {scenarios_path.name} changed since this run started", file=sys.stderr)
        manifest["sessions"].append(now)
    else:
        manifest = {
            **fixed,
            "scenarios_file": str(scenarios_path),
            "scenarios_sha256": scenarios_sha,
            "filler": [{"id": p.id, "words": p.words, "approx_tokens": p.approx_tokens} for p in filler],
            "instructions": INSTRUCTIONS,
            "git_commit": git_commit(),
            "created_at": now,
            "sessions": [now],
        }
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def read_manifest(run_dir: Path) -> dict:
    path = Path(run_dir) / MANIFEST_FILE
    return json.loads(path.read_text()) if path.exists() else {}


def _jsonable(value):
    return json.loads(json.dumps(value))


def git_commit() -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
