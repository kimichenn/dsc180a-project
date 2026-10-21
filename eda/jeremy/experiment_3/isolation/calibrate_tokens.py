"""Validate local token differences against saved Astra usage; no model calls."""
import argparse
import json
from pathlib import Path
import statistics

import collection
import planning
from token_matching import TokenCounter


def calibrate(run, model="gpt-6-astra", encodings=("o200k_base", "cl100k_base")):
    run = Path(run).resolve()
    manifest, trials, worlds = planning.load_plan(run)
    attempts = collection.read_attempts(run, trials, worlds)
    latest = {}
    for attempt in attempts:
        tid = attempt["trial_id"]
        if tid not in latest or attempt["attempt"] > latest[tid]["attempt"]:
            latest[tid] = attempt
    included = [a for a in latest.values() if a["model"] == model and a["eligible"]
                and a["context"] in {"C", "RG"} and a["instruction"] == "none"]
    runtime = json.loads((run / "runtime.json").read_text())
    evidence = []
    for a in sorted(included, key=lambda row: row["trial_id"]):
        folder = run / a["attempt_path"]
        raw = collection.inspect_events(folder / "events.jsonl")
        if raw != a["events"] or type(raw["input_tokens"]) is not int:
            raise ValueError("Calibration requires intact raw events and reported input counts")
        if (folder / "prompt.txt").read_bytes() != (run / a["prompt_path"]).read_bytes():
            raise ValueError("Attempt prompt differs from the frozen prompt")
        if (folder / "system.md").read_bytes() != (run / a["system_path"]).read_bytes():
            raise ValueError("Attempt policy differs from the frozen policy")
        evidence.append({**{k: a[k] for k in ("trial_id", "attempt", "world_id", "effort", "context", "prompt_path", "system_path", "attempt_path")},
                         "reported_input_tokens": raw["input_tokens"],
                         "prompt_sha256": planning.digest(folder / "prompt.txt"),
                         "events_sha256": planning.digest(folder / "events.jsonl"),
                         "system_sha256": planning.digest(folder / "system.md")})
    candidates = []
    for name in encodings:
        counter = TokenCounter({"kind": "tiktoken", "encoding": name})
        rows = []
        for a in evidence:
            local = counter.count((run / a["prompt_path"]).read_text()) + counter.count((run / a["system_path"]).read_text())
            rows.append({**a, "local_input_tokens": local, "unmodeled_input_tokens": a["reported_input_tokens"] - local})
        errors = []
        for wid, effort in sorted({(a["world_id"], a["effort"]) for a in rows}):
            pair = {a["context"]: a for a in rows if (a["world_id"], a["effort"]) == (wid, effort)}
            if set(pair) != {"C", "RG"}:
                raise ValueError("Calibration needs complete C/RG pairs")
            errors.append((pair["RG"]["reported_input_tokens"] - pair["C"]["reported_input_tokens"])
                          - (pair["RG"]["local_input_tokens"] - pair["C"]["local_input_tokens"]))
        if not errors:
            raise ValueError("No calibration pairs")
        overhead = [a["unmodeled_input_tokens"] for a in rows]
        candidates.append({"encoding": name, "tiktoken_version": counter.settings["version"],
                           "paired_observations": len(errors), "worlds": len({a["world_id"] for a in rows}),
                           "max_abs_pair_delta_error_tokens": max(map(abs, errors)),
                           "unmodeled_input_min": min(overhead), "unmodeled_input_max": max(overhead),
                           "unmodeled_input_median": statistics.median(overhead), "observations": rows})
    selected = min(candidates, key=lambda c: c["max_abs_pair_delta_error_tokens"])
    if selected["worlds"] < 5 or selected["paired_observations"] < 5 or selected["max_abs_pair_delta_error_tokens"] > 16:
        raise ValueError("Tokenizer calibration failed: need five worlds and delta errors at most 16 tokens")
    return {"schema_version": 1, "model": model, "created_at": planning.now(),
            "source_run": str(run), "source_manifest_sha256": manifest["manifest_sha256"],
            "runtime": runtime, "selected_encoding": selected["encoding"], "candidates": candidates,
            "status": "empirically_calibrated", "exact_model_tokenizer_verified": False,
            "scope": "Predicts paired text-length differences on saved development inputs; server framing remains unverified",
            "new_model_calls": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output path; calibration evidence is not overwritten")
    report = calibrate(args.run)
    planning.dump(args.output, report)
    print(f"Calibrated {report['selected_encoding']} using saved usage; no model calls made.")
