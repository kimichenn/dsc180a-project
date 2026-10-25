"""Run directories: freeze a run before any call, check it is unchanged before collecting, and keep every attempt.

runs/<name>/
    manifest.json                  the config, the code's commit, the skill's hash, each world's answer, and a hash of every frozen file
    worlds/<world>.json            each world's records and answer key (answer, signature values, chains)
    prompts/<world>_<version>.txt  the exact user message
    system/<instruction>.txt       the exact system prompt
    trials.jsonl                   one row per call, in collection order
    attempts/<trial>/<started>_<operator>.json   one file per call made, never edited
    analysis/                      written by `analyze`; not committed, rebuild it any time

Attempt files are named by start time and operator, so two people collecting into clones of the
same run never write the same file, and git merges their attempts without conflicts.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import random
import re
import subprocess
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import cached_property
from pathlib import Path

from experiment.config import RunConfig, Tier, config_from_dict, config_to_dict
from experiment.generator import generate
from experiment.prompts import SKILL, Prompt, system_prompt, user_prompt
from experiment.world import World

SCHEMA = 2
REPO_ROOT = Path(__file__).resolve().parent.parent
KEY_FIELDS = ("answer", "signatures", "chains")
MAX_CALL_ATTEMPTS = 3  # a call that fails this often is given up on
UNCOUNTED_ERRORS = ("UsageLimitError", "InterruptedCallError")


@dataclass(frozen=True)
class Trial:
    trial_id: str
    order: int
    world_id: str
    version: str
    instruction: str
    model: str
    repeat: int
    tier: int  # 1, or 2 for a tier-2 log's repeats past tier 1's

    @property
    def prompt_file(self) -> str:
        return f"prompts/{self.world_id}_{self.version}.txt"

    @property
    def system_file(self) -> str:
        return f"system/{self.instruction}.txt"


@dataclass
class Run:
    path: Path
    manifest: dict
    trials: list[Trial]

    @cached_property
    def config(self) -> RunConfig:
        return config_from_dict(self.manifest["config"])

    @cached_property
    def keys(self) -> dict[str, dict]:
        """Each world's answer key (answer, signature values, chains), by world id."""
        keys = {}
        for world_id in self.manifest["worlds"]:
            data = json.loads((self.path / "worlds" / f"{world_id}.json").read_text())
            keys[world_id] = {field: data[field] for field in KEY_FIELDS}
        return keys

    def prompt(self, trial: Trial) -> Prompt:
        return Prompt((self.path / trial.system_file).read_text(), (self.path / trial.prompt_file).read_text())


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(config: RunConfig, config_file: Path, run_dir: Path, operator: str) -> Run:
    """Generate the worlds, write every prompt, and freeze the call schedule. No model calls."""
    run_dir = Path(run_dir)
    if run_dir.exists():
        raise ValueError(f"{run_dir} already exists; collect into it, or prepare a new run name")
    state = git_state()  # before writing, so the new run itself does not count as uncommitted work
    if config.purpose == "main":
        check_frozen(config, run_dir, state)
    systems = {name: system_prompt(name) for name in config.tier1.instructions}
    worlds = [generate(seed, config.generator) for seed in config.seeds]
    trials = schedule(config, worlds)

    for folder in ("worlds", "prompts", "system"):
        (run_dir / folder).mkdir(parents=True)
    for name, text in systems.items():
        (run_dir / "system" / f"{name}.txt").write_text(text)
    for world in worlds:
        (run_dir / "worlds" / f"{world.world_id}.json").write_text(_world_json(world))
        for version in config.tier1.versions:
            (run_dir / "prompts" / f"{world.world_id}_{version}.txt").write_text(user_prompt(world.version(version), world.project))
    _write_jsonl(run_dir / "trials.jsonl", [asdict(t) for t in trials])
    frozen = sorted(p for p in run_dir.rglob("*") if p.is_file())
    tier2 = set(config.tier2_seeds)
    manifest = {
        "schema": SCHEMA,
        "run": run_dir.name,
        "created_at": now(),
        "created_by": operator,
        **state,
        "skill_sha256": hashlib.sha256(SKILL.encode()).hexdigest(),
        "config_file": _relative(config_file),
        "config": config_to_dict(config),
        "worlds": {w.world_id: {"seed": w.seed, "project": w.project, "answer": w.answer, "tier2": w.seed in tier2, **w.diagnostics()}
                   for w in worlds},
        "trials": len(trials),
        "files": {str(p.relative_to(run_dir)): sha256(p) for p in frozen},
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return Run(run_dir, manifest, trials)


def check_frozen(config: RunConfig, run_dir: Path, state: dict) -> None:
    """The main run is collected once and is the study's evidence, so it is prepared only from
    committed code with the final skill text, and only on logs no other run has used."""
    if not SKILL.strip():
        raise ValueError("the main run needs the skill: paste its text into SKILL in experiment/prompts.py and commit it")
    if state["git_dirty"] is not False:
        raise ValueError("the main run is prepared only from a clean, committed working tree: commit or stash every change first")
    reused = sorted(_seeds_in_runs(Path(run_dir).parent).intersection(config.seeds))
    if reused:
        raise ValueError(f"seeds {', '.join(map(str, reused[:5]))} are already used by another run; the main run needs fresh logs")


def _seeds_in_runs(folder: Path) -> set[int]:
    """Every seed a prepared run in folder generated its logs from."""
    return {w["seed"] for path in folder.glob("*/manifest.json") for w in json.loads(path.read_text())["worlds"].values()}


def schedule(config: RunConfig, worlds: list[World]) -> list[Trial]:
    """Every call, in collection order: world by world, so a run cut short still has whole worlds;
    shuffled within each world. A tier-2 world keeps its place, and its extra repeats join its
    block, so they are collected alongside its tier-1 repeats."""
    rng = random.Random(config.schedule_seed)
    tier2 = set(config.tier2_seeds)
    trials: list[Trial] = []
    for world in worlds:
        block = _cells(config, 1, config.tier1, 1)
        if world.seed in tier2:
            block += _cells(config, 2, config.tier2, config.tier1.repeats + 1)
        rng.shuffle(block)
        for tier, version, instruction, model, repeat in block:
            trial_id = f"{world.world_id}_{version}_{instruction}_{model}_r{repeat}"
            trials.append(Trial(trial_id, len(trials), world.world_id, version, instruction, model, repeat, tier))
    return trials


def _cells(config: RunConfig, tier: int, design: Tier, first_repeat: int) -> list[tuple[int, str, str, str, int]]:
    """One world's calls in a tier: (tier, version, instruction, model, repeat) for repeats first_repeat..design.repeats."""
    return [(tier, v, i, m, r) for v in design.versions for i in design.instructions for m in config.models
            for r in range(first_repeat, design.repeats + 1)]


def load(run_dir: Path) -> Run:
    """A prepared run, after checking that no frozen file has changed since `prepare`."""
    run_dir = Path(run_dir)
    path = run_dir / "manifest.json"
    if not path.exists():
        raise ValueError(f"{run_dir} is not a prepared run (no manifest.json)")
    manifest = json.loads(path.read_text())
    if manifest.get("schema") != SCHEMA:
        raise ValueError(f"{run_dir} was prepared by an incompatible version of this code")
    changed = [name for name, digest in manifest["files"].items() if not (run_dir / name).exists() or sha256(run_dir / name) != digest]
    if changed:
        raise ValueError(f"frozen files changed since prepare: {', '.join(changed[:5])}; restore them from git or prepare a new run")
    trials = [Trial(**row) for row in _read_jsonl(run_dir / "trials.jsonl")]
    return Run(run_dir, manifest, trials)


def write_attempt(run: Run, record: dict) -> Path:
    folder = run.path / "attempts" / record["trial_id"]
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{datetime.fromisoformat(record['started_at']).strftime('%Y%m%dT%H%M%SZ')}_{record['operator']}"
    path, n = folder / f"{stem}.json", 1
    while path.exists():
        path, n = folder / f"{stem}_{n}.json", n + 1
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, indent=1) + "\n")
    temporary.replace(path)
    return path


def read_attempts(run: Run) -> list[dict]:
    attempts = []
    for path in sorted((run.path / "attempts").glob("*/*.json")):
        attempt = json.loads(path.read_text())
        attempt["file"] = str(path.relative_to(run.path))
        attempts.append(attempt)
    return attempts


def counted(attempts: list[dict]) -> dict[str, dict]:
    """The attempt each trial counts: its earliest valid one, completed with no harness failure."""
    chosen: dict[str, dict] = {}
    for attempt in sorted(attempts, key=lambda a: a["started_at"]):
        if attempt["status"] == "completed" and attempt["eligible"]:
            chosen.setdefault(attempt["trial_id"], attempt)
    return chosen


def counts_toward_cap(attempt: dict) -> bool:
    """A failed attempt that uses up one of a call's MAX_CALL_ATTEMPTS: a harness failure or any saved
    error except a usage-limit stop or a Ctrl-C, which say nothing about the call."""
    if attempt["status"] == "completed":
        return not attempt["eligible"]
    return attempt["error_type"] not in UNCOUNTED_ERRORS


def left_out(attempts: list[dict]) -> set[str]:
    """Trials that failed MAX_CALL_ATTEMPTS times with no valid attempt: never called again, and left out of the analysis."""
    valid = counted(attempts)
    failed = Counter(a["trial_id"] for a in attempts if counts_toward_cap(a))
    return {trial for trial, n in failed.items() if n >= MAX_CALL_ATTEMPTS and trial not in valid}


@contextmanager
def collect_lock(run: Run, operator: str):
    """One collect per run directory on this machine. (Across machines, split the work: see the README.)"""
    path = run.path / ".collect.lock"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        raise ValueError(f"{path} exists: another collect is running on this run. If none is, delete the file.") from None
    with os.fdopen(descriptor, "w") as f:
        json.dump({"pid": os.getpid(), "operator": operator, "started_at": now()}, f)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def operator_name(explicit: str | None = None) -> str:
    """Who is collecting: --operator, else $EXPERIMENT_OPERATOR, else git user.name, else the login name."""
    name = explicit or os.environ.get("EXPERIMENT_OPERATOR") or _git("config", "user.name") or getpass.getuser()
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "unknown"


def git_state() -> dict:
    status = _git("status", "--porcelain")
    return {"git_commit": _git("rev-parse", "HEAD"), "git_dirty": bool(status) if status is not None else None}


def _git(*args: str) -> str | None:
    try:
        done = subprocess.run(["git", *args], capture_output=True, text=True, check=True, cwd=REPO_ROOT)
    except (OSError, subprocess.CalledProcessError):
        return None
    return done.stdout.strip()


def _world_json(world: World) -> str:
    """The world as JSON, one record per line so the file stays readable and small."""
    data = world.to_json()
    records = ",\n".join("  " + json.dumps(r) for r in data.pop("records"))
    head = json.dumps(data, indent=1)
    return f'{head[:-2]},\n "records": [\n{records}\n ]\n}}\n'


def _relative(path: Path) -> str:
    path = Path(path).resolve()
    return str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
