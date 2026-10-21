"""Audit reported pair lengths without discarding outcomes or treating missing as zero."""
from collections import defaultdict


def audit(trials, latest, tolerance):
    groups = defaultdict(dict)
    for trial in trials:
        key = tuple(trial[k] for k in ("world_id", "model", "effort", "instruction"))
        groups[key][trial["context"]] = trial
    rows = []
    for key, pair in sorted(groups.items()):
        if set(pair) != {"R", "RG"}:
            raise ValueError("Reported input auditing requires complete planned R/RG pairs")
        row = dict(zip(("world_id", "model", "effort", "instruction"), key))
        counts, missing = {}, False
        for context, trial in pair.items():
            attempt = latest.get(trial["trial_id"])
            value = attempt["events"]["input_tokens"] if attempt and attempt["eligible"] else None
            counts[context] = value
            row[context + "_input_tokens"] = value
            if attempt and attempt["eligible"] and (type(value) is not int or value <= 0):
                missing = True
        gap = None
        if missing:
            status = "missing_reported_usage"
        elif any(v is None for v in counts.values()):
            status = "pending"
        else:
            gap = abs(counts["R"] - counts["RG"]) / max(counts.values())
            status = "matched" if gap <= tolerance else "input_length_mismatch"
        rows.append({**row, "relative_gap": gap, "tolerance": tolerance, "status": status})
    failed = sum(r["status"] not in {"matched", "pending"} for r in rows)
    matched = sum(r["status"] == "matched" for r in rows)
    return rows, {"planned_pairs": len(rows), "matched_pairs": matched, "failed_pairs": failed,
                  "pending_pairs": sum(r["status"] == "pending" for r in rows),
                  "status": "failed" if failed else ("passed" if matched == len(rows) else "pending")}
