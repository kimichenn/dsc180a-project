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
SOURCE_FILES = ("ledger.py", "planning.py", "collection.py", "run.py", "token_matching.py", "calibrate_tokens.py", "input_matching.py")


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
    for name in ("models", "efforts"):
        if not config[name] or len(set(config[name])) != len(config[name]):
            raise ValueError(f"{name} must be nonempty and unique")
    if config["max_attempts"] < 1 or config["timeout_seconds"] <= 0:
        raise ValueError("Invalid collection limits")
    if not 0 < config["token_match_tolerance"] <= .02:
        raise ValueError("Token tolerance must be positive and at most 2%")
    supported, skipped = matrix(config, catalog)
    counter = ledger.TokenCounter(config["tokenizer"])
    exact = all(counter.exact_for(m["model"]) for m in supported)
    calibration = None
    required_runtime = None
    if stage == "confirmation":
        if not development_reviewed:
            raise ValueError("Review development first; pass --development-reviewed when freezing confirmation")
        if not exact and not allow_estimated_tokens:
            raise ValueError("Server tokenization is unverified; record --allow-estimated-tokens for calibrated local counts plus the mandatory live guard.")
        if len(profile["record_counts"]) != 1 or len(supported) != 1:
            raise ValueError("Freeze one record count and one model/effort for confirmation")
        if config["tokenizer"]["kind"] != "tiktoken":
            raise ValueError("Confirmation requires a calibrated tokenizer, not character estimates")
        evidence_path = ROOT / config["tokenizer_calibration"]["path"]
        if digest(evidence_path) != config["tokenizer_calibration"]["sha256"]:
            raise ValueError("Tokenizer calibration evidence changed")
        calibration = json.loads(evidence_path.read_text())
        candidate = next((c for c in calibration["candidates"] if c["encoding"] == counter.settings["encoding"]), None)
        if (calibration["status"] != "empirically_calibrated" or calibration["model"] != supported[0]["model"]
                or candidate is None or candidate["worlds"] < 5 or candidate["paired_observations"] < 5
                or candidate["max_abs_pair_delta_error_tokens"] > 16
                or candidate["tiktoken_version"] != counter.settings["version"]):
            raise ValueError("Missing or incompatible empirical tokenizer calibration")
        guard = config.get("reported_input_matching", {})
        if not guard.get("enabled") or not 0 < guard.get("tolerance", 0) <= .02:
            raise ValueError("Confirmation requires a reported-input guard at 2% or tighter")
        if profile["contexts"] != ["C", "RG"] or not config.get("pair_adjacent_schedule"):
            raise ValueError("Confirmation requires adjacent C/RG pairs")
        runtime_path = ROOT / config["collection_runtime"]["path"]
        if digest(runtime_path) != config["collection_runtime"]["sha256"]:
            raise ValueError("Collection runtime snapshot changed")
        required_runtime = json.loads(runtime_path.read_text())
        if required_runtime.get("overrides") != calibration["runtime"].get("overrides"):
            raise ValueError("Collection overrides differ from the calibration setup")
    if profile["worlds"] < 1:
        raise ValueError("Use a positive number of worlds")
    if stage == "smoke":
        if profile["worlds"] > 5:
            raise ValueError("Smoke stage has five fixed cases")
        worlds = ledger.smoke_cases()[:profile["worlds"]]
    else:
        if not profile["record_counts"] or len(set(profile["record_counts"])) != len(profile["record_counts"]):
            raise ValueError("Use nonempty, unique record counts")
        seed = profile["seed_start"]
        if stage == "development" and not (300000 <= seed and seed + profile["worlds"] <= 400000):
            raise ValueError("Development seeds must stay within [300000, 400000)")
        if stage == "confirmation" and seed < 400000:
            raise ValueError("Confirmation seeds must start at 400000 or later")
        worlds = [ledger.generate(seed + i, index=i, records=records, nested_rate=profile["nested_rate"])
                  for i in range(profile["worlds"]) for records in profile["record_counts"]]
    if calibration:
        old_worlds = {a["world_id"] for c in calibration["candidates"] for a in c["observations"]}
        if old_worlds.intersection(w["world_id"] for w in worlds):
            raise ValueError("Confirmation worlds overlap calibration/development")
    if not profile["contexts"] or len(set(profile["contexts"])) != len(profile["contexts"]):
        raise ValueError("Use nonempty, unique context conditions")
    if profile["instructions"] != ["none"]:
        raise ValueError("This screen freezes the common instruction only; added skills are a later protocol")
    common = (ROOT / "instructions/common.md").read_text()
    prompts, checks, baselines = {}, [], []
    for world in worlds:
        if not set(profile["contexts"]).issubset(world["contexts"]):
            raise ValueError("Unknown context condition")
        # Generate and validate all four conditions, even if only C/RG are scheduled.
        for rows in world["contexts"].values():
            if ledger.solve(rows)[0] != world["expected"] or ledger.reference_solve(rows) != world["expected"]:
                raise ValueError("Independent answer solvers disagree")
        rendered, counts = ledger.match_texts(
            {c: ledger.render(rows, world["project"]) for c, rows in world["contexts"].items()},
            counter, config["token_match_tolerance"], before=ledger.QUESTION)
        for context, text in rendered.items():
            prompts[f"prompts/{world['world_id']}_{context}.txt"] = text
            baselines.extend({"world_id": world["world_id"], "records": world["records"], "context": context, **row}
                             for row in ledger.shortcuts(world["contexts"][context], world["project"], world["expected"]))
        checks.append({"world_id": world["world_id"], "answer_agreement": True,
                       "prompt_token_counts": counts, "matching_exact_for_all_models": exact,
                       "local_max_gap_tokens": max(counts.values()) - min(counts.values()),
                       "local_relative_gap": (max(counts.values()) - min(counts.values())) / max(counts.values()),
                       "diagnostics": world["diagnostics"],
                       "record_counts": {k: len(v) for k, v in world["contexts"].items()}})
    trials = []
    for world in worlds:
        for context in profile["contexts"]:
            for pair in supported:
                identity = [world["world_id"], context, "none", pair["model"], pair["effort"]]
                prompt_path = f"prompts/{world['world_id']}_{context}.txt"
                trials.append({"trial_id": hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:20],
                               "world_id": world["world_id"], "seed": world["seed"], "records": world["records"],
                               "stage": stage, "context": context, "instruction": "none", **pair,
                               "prompt_path": prompt_path, "system_path": "instructions/none.md",
                               "experimental_prompt_tokens": counter.count(common) + counter.count(prompts[prompt_path]),
                               "prompt_tokens_exact": counter.exact_for(pair["model"])})
    rng = random.Random(config["schedule_seed"])
    if stage == "confirmation":
        blocks = [[t for t in trials if t["world_id"] == w["world_id"]] for w in worlds]
        rng.shuffle(blocks)
        for block in blocks:
            rng.shuffle(block)
        trials = [trial for block in blocks for trial in block]
    else:
        rng.shuffle(trials)
    run.mkdir(parents=True)
    (run / "prompts").mkdir()
    (run / "instructions").mkdir()
    for name, text in prompts.items():
        (run / name).write_text(text)
    (run / "instructions/none.md").write_text(common)
    write_rows(run / "worlds.jsonl", worlds)
    write_rows(run / "trials.jsonl", trials)
    write_csv(run / "unsupported_combinations.csv", skipped, ["model", "effort", "reason"])
    write_csv(run / "baselines.csv", baselines)
    dump(run / "validation.json", {"worlds": checks})
    if calibration:
        dump(run / "tokenizer_calibration.json", calibration)
        dump(run / "runtime_expected.json", required_runtime)
    manifest = {"schema_version": 2, "experiment": "dense_budget_token_matched_v2", "created_at": now(), "stage": stage,
                "config": config, "model_catalog": catalog, "supported_combinations": supported,
                "unsupported_combinations": skipped, "tokenizer": counter.settings,
                "development_reviewed": development_reviewed, "allow_estimated_tokens": allow_estimated_tokens,
                "required_runtime": required_runtime,
                "calibration_runtime_matches_collection": required_runtime == calibration["runtime"] if calibration else None,
                "planned_trials": len(trials),
                "generation_limit": {"requested_tokens": 32000, "enforced": False,
                                     "reason": "No verified Codex CLI output-token cap"},
                "source_hashes": {name: digest(ROOT / name) for name in SOURCE_FILES},
                "artifact_hashes": {str(p.relative_to(run)): digest(p) for p in run.rglob("*") if p.is_file()},
                "limitations": ["New task inspired by Kimi v5, not an exact replication or extension of Experiment 2 accuracy",
                                "Codex harness; requested model is not a pinned served checkpoint",
                                "Model catalog is cached; live availability can differ",
                                "Usage accounting is retained as reported; output/reasoning fields are not added together",
                                "Local text counts empirically calibrated; server tokenizer/framing not independently verified",
                                "Actual reported C/RG input counts must pass the frozen tolerance before confirmation claims",
                                "C/RG combines withdrawals and misleading messages; no added skill"]}
    manifest["manifest_sha256"] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    dump(run / "manifest.json", manifest)
    return manifest

