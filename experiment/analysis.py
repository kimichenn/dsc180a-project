"""Score every counted call and build the tables the proposal reports.

Each trial counts its earliest completed, eligible attempt; any later eligible attempt (the same
trial collected on two machines) is reported and left out. The repeats of one prompt are not
independent samples, so version contrasts first average the repeats within each log, then compare
versions across logs as paired differences with a bootstrap over logs.
"""

from __future__ import annotations

import random
import statistics
from collections import Counter
from dataclasses import asdict

import pandas as pd

from experiment.runs import Run, counted, read_attempts
from experiment.scoring import BUCKETS, hit_length_limit, score

CONTRASTS = (("C", "G"), ("C", "R"), ("C", "RG"), ("R", "RG"))
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 180
CELL = ["model", "instruction", "version"]


def scored_frame(run: Run) -> pd.DataFrame:
    """One row per planned trial; collected ones carry their score, tokens, and who ran them."""
    attempts = read_attempts(run)
    chosen = counted(attempts)
    eligible = Counter(a["trial_id"] for a in attempts if a["status"] == "completed" and a["eligible"])
    rows = []
    for trial in run.trials:
        row = {**asdict(trial), "collected": trial.trial_id in chosen}
        attempt = chosen.get(trial.trial_id)
        if attempt:
            usage = attempt["usage"]
            limit = run.config.models[trial.model].max_output_tokens
            scored = score(attempt["response"], run.keys[trial.world_id], trial.version,
                           hit_length_limit(usage, attempt.get("stop_reason"), limit))
            row.update(scored, record_ids=" ".join(map(str, scored["record_ids"] or [])))
            row.update(
                input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"),
                reasoning_output_tokens=usage.get("reasoning_output_tokens"), turns=usage.get("turns"),
                elapsed_s=attempt["elapsed_s"], operator=attempt["operator"], client_version=attempt["client_version"],
                extra_eligible_attempts=eligible[trial.trial_id] - 1, attempt_file=attempt["file"],
            )
        rows.append(row)
    return pd.DataFrame(rows)


def collected(df: pd.DataFrame) -> pd.DataFrame:
    """The collected rows, with `correct` as a real boolean (it is empty for uncollected rows)."""
    return df[df.collected].astype({"correct": bool})


def accuracy_table(df: pd.DataFrame) -> pd.DataFrame:
    """Accuracy and every bucket's count per model, instruction, and version."""
    done = collected(df)
    table = done.groupby(CELL).agg(
        calls=("correct", "size"), correct=("correct", "sum"),
        mean_input_tokens=("input_tokens", "mean"), mean_output_tokens=("output_tokens", "mean"),
    )
    table.insert(2, "accuracy", table.correct / table.calls)
    wrong = [b for b in BUCKETS if b != "correct"]  # the correct count is already a column
    buckets = pd.crosstab([done.model, done.instruction, done.version], done.bucket).reindex(columns=wrong, fill_value=0)
    return table.join(buckets).reset_index()


def consistency_table(df: pd.DataFrame) -> pd.DataFrame:
    """Per log: how many repeats were right, and for logs never right, whether every repeat gave the same wrong number."""
    rows = []
    for (model, instruction, version, world), group in collected(df).groupby([*CELL, "world_id"]):
        right = int(group.correct.sum())
        pattern = "always" if right == len(group) else "never" if right == 0 else "sometimes"
        wrong = group.loc[~group.correct, "value"]
        rows.append({
            "model": model, "instruction": instruction, "version": version, "world_id": world,
            "repeats": len(group), "correct": right, "pattern": pattern,
            "wrong_values": " ".join("-" if pd.isna(v) else f"{v:g}" for v in wrong),  # - is a gave-up
            # the same wrong number every time is a systematic mistake; different ones, losing track
            "same_wrong_every_time": bool(pattern == "never" and len(group) > 1 and wrong.notna().all() and wrong.nunique() == 1),
        })
    return pd.DataFrame(rows)


def consistency_summary(consistency: pd.DataFrame) -> pd.DataFrame:
    if consistency.empty:
        return consistency
    table = pd.crosstab([consistency.model, consistency.instruction, consistency.version], consistency.pattern)
    table = table.reindex(columns=["always", "sometimes", "never"], fill_value=0)
    table["never_same_wrong"] = consistency.groupby(CELL).same_wrong_every_time.sum()
    return table.reset_index()


def paired_contrasts(df: pd.DataFrame) -> pd.DataFrame:
    """Accuracy gaps between versions on the same logs, in percentage points, with a 95% bootstrap interval over logs."""
    done = collected(df)
    per_log = done.groupby(["model", "instruction", "world_id", "version"]).correct.mean().unstack("version")
    rows = []
    for (model, instruction), table in per_log.groupby(level=["model", "instruction"]):
        for left, right in CONTRASTS:
            if left not in table or right not in table:
                continue
            pairs = table[[left, right]].dropna()
            if pairs.empty:
                continue
            gaps = (pairs[left] - pairs[right]).tolist()
            low, high = bootstrap(gaps)
            rows.append({
                "model": model, "instruction": instruction, "contrast": f"{left} - {right}", "logs": len(gaps),
                "left_accuracy": pairs[left].mean(), "right_accuracy": pairs[right].mean(),
                "gap_pp": 100 * statistics.mean(gaps), "ci_low_pp": 100 * low, "ci_high_pp": 100 * high,
            })
    return pd.DataFrame(rows)


def bootstrap(values: list[float]) -> tuple[float, float]:
    rng = random.Random(BOOTSTRAP_SEED)
    draws = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(BOOTSTRAP_DRAWS))
    return draws[round(0.025 * (BOOTSTRAP_DRAWS - 1))], draws[round(0.975 * (BOOTSTRAP_DRAWS - 1))]


def analyze(run: Run) -> str:
    """Write the tables to <run>/analysis/ and return a text report."""
    df = scored_frame(run)
    tables = {"scored": df}
    lines = [f"{run.path.name}: {int(df.collected.sum())} of {len(df)} planned calls collected"]
    if df.collected.any():
        consistency = consistency_table(df)
        tables.update(
            accuracy=accuracy_table(df), consistency=consistency,
            consistency_summary=consistency_summary(consistency), contrasts=paired_contrasts(df),
        )
        done = collected(df)
        lines += _section("Accuracy and buckets", tables["accuracy"].drop(columns=["mean_input_tokens", "mean_output_tokens"]))
        lines += _section("Version gaps on the same logs (repeats averaged per log; 95% bootstrap CI)", tables["contrasts"])
        if run.config.repeats > 1:
            lines += _section("Consistency across repeats (logs per pattern)", tables["consistency_summary"])
        lines += _section("Tokens", tables["accuracy"][[*CELL, "mean_input_tokens", "mean_output_tokens"]])
        notes = []
        extra = int(done.extra_eligible_attempts.sum())
        if extra:
            notes.append(f"{extra} extra eligible attempts left out (a trial collected more than once; the earliest counts)")
        limited = done[done.hit_length_limit]
        if len(limited):
            notes.append(f"{len(limited)} responses hit the output limit (hit_length_limit): {int((limited.bucket == 'cut_off').sum())} "
                         "had no ANSWER line (cut_off); the rest are scored on their final ANSWER line")
        for model, versions in done.groupby("model").client_version.unique().items():
            if len(versions) > 1:
                notes.append(f"{model} was collected with several CLI versions: {', '.join(sorted(versions))}")
        if notes:
            lines += ["", "Notes:", *(f"  - {note}" for note in notes)]
    out = run.path / "analysis"
    out.mkdir(exist_ok=True)
    for name, table in tables.items():
        table.to_csv(out / f"{name}.csv", index=False)
    report = "\n".join(lines)
    (out / "report.txt").write_text(report + "\n")
    return report


def _section(title: str, table: pd.DataFrame) -> list[str]:
    if table.empty:
        return ["", title, "  (none yet)"]
    return ["", title, table.to_string(index=False, float_format=lambda x: f"{x:.2f}")]
