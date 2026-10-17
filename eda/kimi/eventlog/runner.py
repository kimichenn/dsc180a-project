"""Plan a stage's calls, save its generated logs, and run the calls (resumable, concurrent)."""

from __future__ import annotations

import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from eventlog.checks import check_log
from eventlog.dials import SEEDS, Dials, stage_settings
from eventlog.generator import Log, generate
from eventlog.prompts import INSTRUCTIONS, build_prompt
from eventlog.scoring import parse_answer
from harness.calls import FatalModelError, generate_with_retries
from harness.models import ModelClient, ModelConfig
from harness.runs import CHARS_PER_TOKEN, RESPONSES_FILE, load_responses, token_counts

LOGS_DIR = "logs"


@dataclass(frozen=True)
class Job:
    stage: str
    setting: str
    seed: int
    version: str
    instruction: str
    model: str

    @property
    def log_id(self) -> str:
        return f"{self.setting}_seed{self.seed}"

    @property
    def id(self) -> str:
        return "|".join([self.setting, f"seed{self.seed}", self.version, self.instruction, self.model])


@dataclass
class RunSummary:
    attempted: int
    succeeded: int
    failed: int
    format_failures: int
    skipped: int


def plan(stage: str, base: Dials, models: list[str], shuffle_seed: int = 0) -> tuple[list[Job], dict[str, Log]]:
    """Every call for a stage, in interleaved random order, plus the logs they use (all checked)."""
    instructions = tuple(INSTRUCTIONS) if stage == "C" else ("none",)
    jobs, logs = [], {}
    for setting in stage_settings(stage, base):
        for seed in SEEDS[stage]:
            log = generate(setting.dials, seed)
            problems = check_log(log)
            if problems:
                raise ValueError(f"log {setting.label} seed {seed} failed generator checks: {'; '.join(problems[:3])}")
            logs[f"{setting.label}_seed{seed}"] = log
            for version in setting.versions:
                for instruction in instructions:
                    jobs += [Job(stage, setting.label, seed, version, instruction, model) for model in models]
    random.Random(shuffle_seed).shuffle(jobs)
    return jobs, logs


def save_logs(run_dir: Path, logs: dict[str, Log]) -> None:
    folder = Path(run_dir) / LOGS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    for log_id, log in logs.items():
        record = {**log.metadata(), "conflict": log.render("conflict"), "consistent": log.render("consistent")}
        (folder / f"{log_id}.json").write_text(json.dumps(record, indent=1) + "\n")


def load_log_files(run_dir: Path) -> dict[str, dict]:
    folder = Path(run_dir) / LOGS_DIR
    return {path.stem: json.loads(path.read_text()) for path in sorted(folder.glob("*.json"))}


def estimate_cost(jobs: list[Job], logs: dict[str, Log], configs: dict[str, ModelConfig], response_format: str, output_tokens: int) -> list[dict]:
    """Rough cost per model: prompt tokens from measured characters per token, plus an assumed output length per call."""
    texts = {(log_id, version): log.render(version) for log_id, log in logs.items() for version in ("conflict", "consistent")}
    rows = {name: {"model": name, "calls": 0, "input_tokens": 0, "output_tokens": 0} for name in configs}
    for job in jobs:
        prompt = build_prompt(texts[(job.log_id, job.version)], logs[job.log_id].question, job.instruction, response_format)
        row = rows[job.model]
        row["calls"] += 1
        chars = len(prompt.system) + len(prompt.messages[0]["content"])
        row["input_tokens"] += round(chars / CHARS_PER_TOKEN[configs[job.model].provider])
        row["output_tokens"] += output_tokens
    for name, row in rows.items():
        c = configs[name]
        if c.input_price is not None and c.output_price is not None:
            row["usd"] = round((row["input_tokens"] * c.input_price + row["output_tokens"] * c.output_price) / 1e6, 2)
    return list(rows.values())


def run_jobs(
    jobs: list[Job],
    log_files: dict[str, dict],
    clients: dict[str, ModelClient],
    run_dir: Path,
    response_format: str,
    workers: int = 4,
) -> RunSummary:
    run_dir = Path(run_dir)
    done = {row["job_id"] for row in load_responses(run_dir)}
    pending = [j for j in jobs if j.id not in done]
    succeeded = failed = format_failures = 0
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        with open(run_dir / RESPONSES_FILE, "a") as out:
            futures = [pool.submit(_execute, j, clients[j.model], log_files[j.log_id], response_format) for j in pending]
            for count, future in enumerate(as_completed(futures), 1):
                row = future.result()  # raises FatalModelError
                out.write(json.dumps(row) + "\n")
                out.flush()
                if row["error"] is not None:
                    failed += 1
                    print(f"\n  error on {row['job_id']}: {row['error']}", file=sys.stderr)
                else:
                    succeeded += 1
                    format_failures += row["format_failure"]
                print(f"\r  {count}/{len(pending)} done, {failed} errors", end="", file=sys.stderr, flush=True)
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
        if pending:
            print(file=sys.stderr)
    return RunSummary(len(pending), succeeded, failed, format_failures, len(jobs) - len(pending))


def _execute(job: Job, client: ModelClient, log_file: dict, response_format: str) -> dict:
    prompt = build_prompt(log_file[job.version], log_file["question"], job.instruction, response_format)
    row = {
        "job_id": job.id,
        "log_id": job.log_id,
        **asdict(job),
        **client.config.record(),
        "response_format": response_format,
        "system": prompt.system,
    }
    started = time.monotonic()
    try:
        attempts = [generate_with_retries(client, prompt)]
        if parse_answer(attempts[0].text) is None:
            attempts.append(generate_with_retries(client, prompt))  # protocol: rerun once
        final = attempts[-1]
        tokens = [token_counts(a.usage) for a in attempts]
        row.update(
            response=final.text,
            first_response=attempts[0].text if len(attempts) > 1 else None,
            attempts=len(attempts),
            format_failure=parse_answer(final.text) is None,
            finish_reason=final.finish_reason,
            model_version=final.model_version,
            input_tokens=sum(t[0] for t in tokens),
            output_tokens=sum(t[1] for t in tokens),
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
