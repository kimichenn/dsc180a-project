"""A run directory: append-only responses.jsonl (one row per call, keyed by job_id) and a manifest.json
that refuses to mix two different plans. Also token counting across providers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from harness.calls import git_commit

RESPONSES_FILE = "responses.jsonl"
MANIFEST_FILE = "manifest.json"
# Measured on the v4 logs, whose made-up project names split into many tokens (most of all for Claude).
CHARS_PER_TOKEN = {"openai": 3.0, "codex": 3.0, "anthropic": 1.8, "claude-code": 1.8, "google": 2.8}


def read_rows(run_dir: Path) -> list[dict]:
    path = Path(run_dir) / RESPONSES_FILE
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_responses(run_dir: Path) -> list[dict]:
    """The latest successful response per job."""
    latest = {}
    for row in read_rows(run_dir):
        if row.get("error") is None:
            latest[row["job_id"]] = row
    return list(latest.values())


def write_manifest(run_dir: Path, fixed: dict, created: dict | None = None) -> dict:
    """Record the run controls; refuse to mix two different plans in one run directory.
    `fixed` must match on every session; `created` is stored once and never compared."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / MANIFEST_FILE
    fixed = json.loads(json.dumps(fixed))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if path.exists():
        manifest = json.loads(path.read_text())
        for key, value in fixed.items():
            if manifest.get(key) != value:
                raise ValueError(f"{run_dir} was started with a different {key}; use a new --out directory")
        manifest["sessions"].append(now)
    else:
        manifest = {**fixed, **(created or {}), "git_commit": git_commit(), "created_at": now, "sessions": [now]}
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def read_manifest(run_dir: Path) -> dict:
    path = Path(run_dir) / MANIFEST_FILE
    return json.loads(path.read_text()) if path.exists() else {}


def token_counts(usage: dict) -> tuple[int, int]:
    """(input, output) tokens from any provider's usage block; output includes reasoning tokens."""
    if "prompt_token_count" in usage:  # Gemini
        output = (usage.get("candidates_token_count") or 0) + (usage.get("thoughts_token_count") or 0)
        return usage.get("prompt_token_count") or 0, output
    # Claude reports cache reads and writes apart from input_tokens; OpenAI counts them inside it.
    cached = (usage.get("cache_creation_input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0)
    return (usage.get("input_tokens") or 0) + cached, usage.get("output_tokens") or 0
