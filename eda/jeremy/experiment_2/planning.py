"""Freeze datasets and supported model/effort matrices before any collection."""
import csv
import hashlib
import json
import os
from pathlib import Path
import random
from datetime import datetime, timezone

import ledger

ROOT = Path(__file__).resolve().parent
SOURCE_FILES = ("ledger.py", "planning.py", "collection.py", "run.py")


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_rows(path, rows):
    temporary = Path(str(path) + ".tmp")
    temporary.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    temporary.replace(path)


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_csv(path, rows, fields=None):
    rows = list(rows)
    fields = fields or list(dict.fromkeys(k for row in rows for k in row))
    temporary = Path(str(path) + ".tmp")
    with temporary.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v for k, v in row.items()})
    temporary.replace(path)


def load_catalog(path=None):
    source = Path(path) if path else Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "models_cache.json"
    if not source.exists():
        raise ValueError("No Codex model catalog found. Open Codex once to refresh it, or pass --catalog PATH.")
    raw = json.loads(source.read_text())
    models = []
    for model in raw.get("models", []):
        levels = model.get("supported_reasoning_levels", [])
        models.append({"model": model.get("slug"), "efforts": [v["effort"] if isinstance(v, dict) else v for v in levels],
                       "context_window": model.get("context_window"), "visibility": model.get("visibility"),
                       "default_effort": model.get("default_reasoning_level")})
    if not models:
        raise ValueError("Catalog has no models")
    return {"source": str(source), "fetched_at": raw.get("fetched_at"), "client_version": raw.get("client_version"), "models": models}


def matrix(config, catalog):
    advertised = {m["model"]: m for m in catalog["models"]}
    supported, skipped = [], []
    for model in config["models"]:
        for effort in config["efforts"]:
            pair = {"model": model, "effort": effort}
            if model not in advertised:
                skipped.append({**pair, "reason": "model_not_in_codex_catalog"})
            elif effort not in advertised[model]["efforts"]:
                skipped.append({**pair, "reason": "effort_not_advertised_by_codex"})
            elif effort == "ultra":
                skipped.append({**pair, "reason": "ultra_delegation_is_outside_single_model_protocol"})
            else:
                supported.append(pair)
    if not supported:
        raise ValueError("No supported model/effort combinations; check config and catalog")
    return supported, skipped


def load_plan(run, check_sources=False):
    run = Path(run).resolve()
    manifest = json.loads((run / "manifest.json").read_text())
    saved_hash = manifest.pop("manifest_sha256")
    actual_hash = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    if saved_hash != actual_hash:
        raise ValueError("Frozen manifest changed; create a new run")
    manifest["manifest_sha256"] = saved_hash
    for name, expected in manifest["artifact_hashes"].items():
        if digest(run / name) != expected:
            raise ValueError(f"Frozen artifact changed: {name}. Create a new run.")
    if check_sources:
        for name, expected in manifest["source_hashes"].items():
            if digest(ROOT / name) != expected:
                raise ValueError(f"Collector code changed: {name}. Create a new run.")
    return manifest, read_rows(run / "trials.jsonl"), {row["world_id"]: row for row in read_rows(run / "worlds.jsonl")}


def prepare(run, config, stage, catalog, allow_estimated_tokens=False, development_reviewed=False):
    run = Path(run).resolve()
    if run.exists():
        raise ValueError("Run directory already exists; use collect to resume or choose a new name")
    profile = config["profiles"][stage]
    if not config["models"] or len(set(config["models"])) != len(config["models"]):
        raise ValueError("Model IDs must be nonempty and unique")
    if not config["efforts"] or len(set(config["efforts"])) != len(config["efforts"]):
        raise ValueError("Effort levels must be nonempty and unique")
    if config["max_attempts"] < 1 or config["timeout_seconds"] <= 0:
        raise ValueError("Invalid collection limits")
    if not 0 < config["token_match_tolerance"] <= .02:
        raise ValueError("Token tolerance must be positive and at most 2%")
    supported, skipped = matrix(config, catalog)
    counter = ledger.TokenCounter(config["tokenizer"])
    exact = all(counter.exact_for(m["model"]) for m in supported)
    if stage == "confirmation":
        if not development_reviewed:
            raise ValueError("Review development first; pass --development-reviewed when freezing confirmation")
        if not exact and not allow_estimated_tokens:
            raise ValueError("Exact token matching is unverified. Configure a verified tokenizer or explicitly record --allow-estimated-tokens.")
        if len(profile["depths"]) != 1:
            raise ValueError("Freeze exactly one depth for confirmation")
    if stage == "smoke":
        worlds = ledger.smoke_cases()[:profile["worlds"]]
        if not worlds or profile["worlds"] > 5:
            raise ValueError("Smoke stage has five fixed cases")
    else:
        if profile["worlds"] < 1 or len(set(profile["depths"])) != len(profile["depths"]):
            raise ValueError("Use positive worlds and unique depths")
        # Disjoint seed ranges protect the confirmation set from development reuse.
        if stage == "development" and not (100000 <= profile["seed_start"] < 200000):
            raise ValueError("Development seeds must start in [100000, 200000)")
        if stage == "confirmation" and profile["seed_start"] < 200000:
            raise ValueError("Confirmation seeds must start at 200000 or later")
        if stage == "development" and profile["seed_start"] + profile["worlds"] > 200000:
            raise ValueError("Development seeds overlap confirmation range")
        worlds = [ledger.generate(profile["seed_start"] + i, index=i, depth=depth,
                                  **{k: profile[k] for k in ("records", "projects", "approvals", "summaries")})
                  for i in range(profile["worlds"]) for depth in profile["depths"]]
    if len(set(profile["contexts"])) != len(profile["contexts"]) or len(set(profile["instructions"])) != len(profile["instructions"]):
        raise ValueError("Duplicate treatment labels")
    if not profile["contexts"] or not profile["instructions"]:
        raise ValueError("Empty treatments")
    if not set(profile["instructions"]).issubset({"none", "neutral", "skill"}):
        raise ValueError("Unknown instruction treatment")
    common = (ROOT / "instructions/common.md").read_text()
    blocks, block_counts = ledger.match_texts(
        {k: (ROOT / f"instructions/{k}.md").read_text() for k in ("neutral", "skill")},
        counter, config["token_match_tolerance"],
    )
    systems = {"none": common, **{k: common + "\n" + v for k, v in blocks.items()}}
    prompts, checks, baselines = {}, [], []
    for world in worlds:
        if not set(profile["contexts"]).issubset(world["contexts"]):
            raise ValueError("Unknown context condition")
        rendered, counts = ledger.match_texts(
            {c: ledger.render(rows, world["project"]) for c, rows in world["contexts"].items()},
            counter, config["token_match_tolerance"], before="\nWhich route is authorized",
        )
        for context, text in rendered.items():
            prompts[f"prompts/{world['world_id']}_{context}.txt"] = text
            baselines.extend({"world_id": world["world_id"], "depth": world["depth"], "context": context, **row}
                             for row in ledger.shortcuts(world["contexts"][context], world["project"], world["expected"]))
        checks.append({"world_id": world["world_id"], "answer_agreement": True,
                       "prompt_token_counts": counts, "matching_exact_for_all_models": exact,
                       "record_counts": {k: len(v) for k, v in world["contexts"].items()}})
    trials = []
    for world in worlds:
        for context in profile["contexts"]:
            for instruction in profile["instructions"]:
                for pair in supported:
                    identity = [world["world_id"], context, instruction, pair["model"], pair["effort"]]
                    trial_id = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:20]
                    prompt_path = f"prompts/{world['world_id']}_{context}.txt"
                    trials.append({"trial_id": trial_id, "world_id": world["world_id"], "seed": world["seed"],
                                   "depth": world["depth"], "stage": stage, "context": context, "instruction": instruction,
                                   **pair, "prompt_path": prompt_path, "system_path": f"instructions/{instruction}.md",
                                   "experimental_prompt_tokens": counter.count(systems[instruction] + prompts[prompt_path]),
                                   "prompt_tokens_exact": counter.exact_for(pair["model"])})
    random.Random(config["schedule_seed"]).shuffle(trials)
    run.mkdir(parents=True)
    (run / "prompts").mkdir()
    (run / "instructions").mkdir()
    for name, text in prompts.items():
        (run / name).write_text(text)
    for name, text in systems.items():
        (run / f"instructions/{name}.md").write_text(text)
    write_rows(run / "worlds.jsonl", worlds)
    write_rows(run / "trials.jsonl", trials)
    write_csv(run / "unsupported_combinations.csv", skipped, ["model", "effort", "reason"])
    write_csv(run / "baselines.csv", baselines)
    dump(run / "validation.json", {"worlds": checks, "instruction_token_counts": block_counts})
    manifest = {"schema_version": 1, "created_at": now(), "stage": stage, "config": config,
                "model_catalog": catalog, "supported_combinations": supported, "unsupported_combinations": skipped,
                "tokenizer": counter.settings, "development_reviewed": development_reviewed,
                "allow_estimated_tokens": allow_estimated_tokens, "planned_trials": len(trials),
                "generation_limit": {"requested_tokens": 32000, "enforced": False, "reason": "No verified Codex CLI output-token cap"},
                "source_hashes": {name: digest(ROOT / name) for name in SOURCE_FILES},
                "artifact_hashes": {str(p.relative_to(run)): digest(p) for p in run.rglob("*") if p.is_file()},
                "limitations": ["Codex harness; requested model is not a pinned served checkpoint",
                                "Model catalog is cached; live availability can differ",
                                "Usage accounting is retained as reported; output/reasoning fields are not added together",
                                "Exact prompt token matching unverified" if not exact else "Prompt counts use configured verified tokenizer"]}
    manifest["manifest_sha256"] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    dump(run / "manifest.json", manifest)
    return manifest
