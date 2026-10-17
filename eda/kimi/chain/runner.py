"""Plan a phase's calls, save its chains, and run the calls: resumable, concurrent, and capped in API spend.

Subscription models (Codex, Claude Code) cost nothing per call. API-billed models count against
BUDGET_USD, summed over every responses.jsonl under results/v5. Before an API call starts, its
worst case (full output limit, plus the one rerun for a missing ANSWER line) is reserved, so the
total never passes the cap even with calls in flight.
"""

from __future__ import annotations

import json
import random
import sys
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from chain.dials import BREAK_SEEDS, SWEEP_SEED_START, SWEEP_SEEDS, Profile
from chain.generator import Chain, generate
from chain.prompts import build_prompt
from chain.scoring import parse_answer
from harness.calls import FatalModelError, generate_with_retries
from harness.models import SUBSCRIPTION_PROVIDERS, ModelClient, ModelConfig
from harness.runs import CHARS_PER_TOKEN, RESPONSES_FILE, load_responses, token_counts

CHAINS_DIR = "chains"
VERSIONS = ("conflict", "control")
BUDGET_USD = 10.0  # API spend cap across all v5 runs
MAX_ERRORS_IN_A_ROW = 3  # then stop that model for this session (e.g. a subscription usage limit)


@dataclass(frozen=True)
class Job:
    phase: str
    n: int
    seed: int
    version: str
    instruction: str
    model: str

    @property
    def chain_id(self) -> str:
        return f"n{self.n}_seed{self.seed}"

    @property
    def id(self) -> str:
        return "|".join([self.chain_id, self.version, self.instruction, self.model])


@dataclass
class Plan:
    jobs: list[Job]
    chains: dict[str, Chain]
    prompt_chars: dict[tuple[str, str], int]  # (chain_id, version) -> system + user characters
    skipped: list[str] = field(default_factory=list)


@dataclass
class RunSummary:
    attempted: int
    succeeded: int
    failed: int
    format_failures: int
    tool_calls: int
    already_done: int
    over_budget: int
    stopped: dict[str, str]
    spent_usd: float


def seeds_for(phase: str) -> tuple[int, ...]:
    return BREAK_SEEDS if phase == "break" else tuple(range(SWEEP_SEED_START, SWEEP_SEED_START + SWEEP_SEEDS))


def plan(phase: str, profile: Profile, levels: list[int], configs: dict[str, ModelConfig], instruction: str = "none", shuffle_seed: int = 0) -> Plan:
    """Every call for a phase in shuffled order. Levels too small for the profile, and (model, N)
    pairs whose prompt would not fit the model's context window, are skipped with a reason."""
    jobs, chains, chars, skipped = [], {}, {}, []
    for n in levels:
        try:
            level = {seed: generate(n, profile, seed) for seed in seeds_for(phase)}
        except ValueError as error:
            skipped.append(f"N={n} for every model: {error}")
            continue
        for seed, chain in level.items():
            chains[f"n{n}_seed{seed}"] = chain
            for version in VERSIONS:
                prompt = build_prompt(chain.render(version), chain.question, instruction, profile.response_format)
                chars[(f"n{n}_seed{seed}", version)] = len(prompt.system) + len(prompt.messages[0]["content"])
        longest = max(chars[(f"n{n}_seed{seed}", v)] for seed in level for v in VERSIONS)
        for name, config in configs.items():
            tokens = longest / CHARS_PER_TOKEN[config.provider]
            if config.context_window and tokens > config.context_window:
                skipped.append(f"{name} at N={n}: ~{tokens:,.0f} prompt tokens > {config.context_window:,} context window")
                continue
            jobs += [Job(phase, n, seed, version, instruction, name) for seed in level for version in VERSIONS]
    random.Random(shuffle_seed).shuffle(jobs)
    return Plan(jobs, chains, chars, skipped)


def save_chains(run_dir: Path, chains: dict[str, Chain]) -> None:
    folder = Path(run_dir) / CHAINS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    for chain_id, chain in chains.items():
        record = {**chain.metadata(), "conflict": chain.render("conflict"), "control": chain.render("control")}
        (folder / f"{chain_id}.json").write_text(json.dumps(record, indent=1) + "\n")


def load_chain_files(run_dir: Path) -> dict[str, dict]:
    return {path.stem: json.loads(path.read_text()) for path in sorted((Path(run_dir) / CHAINS_DIR).glob("*.json"))}


def billed(config: ModelConfig) -> bool:
    return config.provider not in SUBSCRIPTION_PROVIDERS


def call_usd(config: ModelConfig, usage: dict) -> float:
    if not billed(config) or config.input_price is None or config.output_price is None:
        return 0.0
    tokens_in, tokens_out = token_counts(usage)
    return (tokens_in * config.input_price + tokens_out * config.output_price) / 1e6


def worst_usd(config: ModelConfig, prompt_chars: int) -> float:
    """The most one job can bill: the full output limit, twice (the rerun for a missing ANSWER line)."""
    if not billed(config):
        return 0.0
    tokens_in = prompt_chars / CHARS_PER_TOKEN[config.provider]
    return 2 * (tokens_in * (config.input_price or 0) + config.max_output_tokens * (config.output_price or 0)) / 1e6


def spent_usd(results_root: Path) -> float:
    """API spend recorded in every run directory under results_root."""
    total = 0.0
    for path in Path(results_root).rglob(RESPONSES_FILE):
        for line in path.read_text().splitlines():
            if line.strip():
                total += json.loads(line).get("usd") or 0.0
    return total


def estimate(jobs: list[Job], prompt_chars: dict, configs: dict[str, ModelConfig], output_tokens: int) -> list[dict]:
    """Per model: calls, prompt tokens, and for billed models the expected and worst-case cost."""
    rows = {name: {"model": name, "billed": billed(c), "calls": 0, "input_tokens": 0, "expected_usd": 0.0, "worst_usd": 0.0} for name, c in configs.items()}
    for job in jobs:
        config, chars = configs[job.model], prompt_chars[(job.chain_id, job.version)]
        row = rows[job.model]
        row["calls"] += 1
        row["input_tokens"] += round(chars / CHARS_PER_TOKEN[config.provider])
        if row["billed"]:
            row["expected_usd"] += call_usd(config, {"input_tokens": chars / CHARS_PER_TOKEN[config.provider], "output_tokens": output_tokens})
            row["worst_usd"] += worst_usd(config, chars)
    return list(rows.values())


def run_jobs(
    jobs: list[Job],
    chain_files: dict[str, dict],
    clients: dict[str, ModelClient],
    prompt_chars: dict,
    run_dir: Path,
    budget_left: float,
    workers: int = 4,
) -> RunSummary:
    run_dir = Path(run_dir)
    done = {row["job_id"] for row in load_responses(run_dir)}
    queue = [j for j in jobs if j.id not in done]
    attempted = len(queue)
    succeeded = failed = format_failures = tool_calls = 0
    spent = reserved = 0.0
    streak: Counter = Counter()
    stopped: dict[str, str] = {}
    running = {}
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        with open(run_dir / RESPONSES_FILE, "a") as out:
            while queue or running:
                i = 0
                while len(running) < workers and i < len(queue):
                    job = queue[i]
                    if job.model in stopped:
                        i += 1
                        continue
                    cost = worst_usd(clients[job.model].config, prompt_chars[(job.chain_id, job.version)])
                    if spent + reserved + cost > budget_left:
                        i += 1  # leave it for later; subscription jobs behind it can still start
                        continue
                    queue.pop(i)
                    reserved += cost
                    running[pool.submit(_execute, job, clients[job.model], chain_files[job.chain_id])] = (job, cost)
                if not running:
                    break  # everything left is over budget or belongs to a stopped model
                finished, _ = wait(running, return_when=FIRST_COMPLETED)
                for future in finished:
                    job, cost = running.pop(future)
                    reserved -= cost
                    row = future.result()  # raises FatalModelError
                    out.write(json.dumps(row) + "\n")
                    out.flush()
                    spent += row["usd"]
                    if row["error"] is not None:
                        failed += 1
                        streak[job.model] += 1
                        print(f"\n  error on {row['job_id']}: {row['error']}", file=sys.stderr)
                        if streak[job.model] >= MAX_ERRORS_IN_A_ROW and job.model not in stopped:
                            stopped[job.model] = row["error"]
                            print(f"\n  stopping {job.model} for this session after {MAX_ERRORS_IN_A_ROW} errors in a row", file=sys.stderr)
                    else:
                        succeeded += 1
                        streak[job.model] = 0
                        format_failures += row["format_failure"]
                        tool_calls += row["tool_calls"] > 0
                    count = succeeded + failed
                    print(f"\r  {count}/{attempted} done, {failed} errors, ${spent:.2f} API spend", end="", file=sys.stderr, flush=True)
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
        if attempted:
            print(file=sys.stderr)
    over_budget = sum(1 for j in queue if j.model not in stopped)
    return RunSummary(attempted, succeeded, failed, format_failures, tool_calls, len(jobs) - attempted, over_budget, stopped, spent)


def _execute(job: Job, client: ModelClient, chain_file: dict) -> dict:
    response_format = chain_file["profile"]["response_format"]
    prompt = build_prompt(chain_file[job.version], chain_file["question"], job.instruction, response_format)
    row = {
        "job_id": job.id,
        "chain_id": job.chain_id,
        **asdict(job),
        **client.config.record(),
        "harness": getattr(client, "version", None),  # CLI version for subscription models
        "response_format": response_format,
        "system": prompt.system,
    }
    started = time.monotonic()
    attempts = []
    try:
        attempts.append(generate_with_retries(client, prompt))
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
            tool_calls=sum(a.usage.get("tool_calls", 0) for a in attempts),
            continuations=sum(a.usage.get("continuations", 0) for a in attempts),
            error=None,
        )
    except FatalModelError:
        raise
    except Exception as error:
        row.update(response=None, error=f"{type(error).__name__}: {error}")
    row.update(
        usd=round(sum(call_usd(client.config, a.usage) for a in attempts), 6),
        latency_s=round(time.monotonic() - started, 2),
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    return row
