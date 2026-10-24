"""Score every counted call and build the tables the design reports.

Each trial counts its earliest completed, eligible attempt; any later eligible attempt (the same
trial collected on two machines) is reported and left out. The repeats of one prompt are not
independent, so every comparison first averages the repeats within each log, then compares
conditions on the same logs as paired differences.

Primary comparisons, for each model (positive means the first condition does better):
    C - R, no skill                    do withdrawals hurt?
    E - R, no skill                    is it the withdrawal logic, or just the extra numbers?
    skill gain on R - skill gain on E  does the skill fix withdrawals specifically?
Each gets a 95% bootstrap interval over logs and a two-sided paired permutation p-value (random
sign flips of each log's difference), Holm-corrected across every primary comparison of every
model. All other comparisons are exploratory and uncorrected.
"""

from __future__ import annotations

import random
import statistics
from collections import Counter
from dataclasses import asdict

import pandas as pd

from experiment.records import VERSIONS
from experiment.runs import Run, counted, read_attempts
from experiment.scoring import BUCKETS, hit_length_limit, score

SEED = 180
BOOTSTRAP_DRAWS = 2000
PERMUTATIONS = 10_000
CELL = ["model", "instruction", "version"]

# A comparison weights each log's accuracy in some (instruction, version) cells and sums them.
Comparison = dict[tuple[str, str], int]
PRIMARY: dict[str, Comparison] = {
    "C - R (no skill)": {("none", "C"): 1, ("none", "R"): -1},
    "E - R (no skill)": {("none", "E"): 1, ("none", "R"): -1},
    "skill gain on R - skill gain on E": {("skill", "R"): 1, ("none", "R"): -1, ("skill", "E"): -1, ("none", "E"): 1},
}


def _exploratory() -> dict[str, Comparison]:
    comparisons = {}
    for arm, label in (("none", "no skill"), ("skill", "skill")):
        for left, right in (("C", "R"), ("E", "R"), ("R", "RG"), ("C", "E"), ("C", "RG"), ("C", "G")):
            comparisons[f"{left} - {right} ({label})"] = {(arm, left): 1, (arm, right): -1}
    for version in VERSIONS:
        comparisons[f"skill - no skill on {version}"] = {("skill", version): 1, ("none", version): -1}
    return {name: weights for name, weights in comparisons.items() if name not in PRIMARY}


EXPLORATORY = _exploratory()
# Failure-bucket rates compared with the baselines: C has no withdrawals, E has their numbers without their logic.
EXCESS = (("R", "C"), ("RG", "C"), ("E", "C"), ("R", "E"))


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
            scored = score(attempt["response"], run.keys[trial.world_id], hit_length_limit(usage, attempt.get("stop_reason"), limit))
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
    failures = [b for b in BUCKETS if b != "correct"]  # the correct count is already a column
    buckets = pd.crosstab([done.model, done.instruction, done.version], done.bucket).reindex(columns=failures, fill_value=0)
    return _in_version_order(table.join(buckets).reset_index())


def comparison_table(df: pd.DataFrame) -> pd.DataFrame:
    """Every primary and exploratory comparison the collected cells allow, in percentage points."""
    done = collected(df)
    per_log = done.groupby(["model", "world_id", "instruction", "version"]).correct.mean().unstack(["instruction", "version"])
    rows = []
    for model, table in per_log.groupby(level="model"):
        table = table.dropna(axis=1, how="all")
        for family, comparisons in (("primary", PRIMARY), ("exploratory", EXPLORATORY)):
            for name, weights in comparisons.items():
                if any(cell not in table.columns for cell in weights):
                    continue
                cells = table[list(weights)].dropna()
                if cells.empty:
                    continue
                differences = sum(cells[cell] * weight for cell, weight in weights.items()).tolist()
                low, high = bootstrap(differences)
                rows.append({
                    "family": family, "model": model, "comparison": name, "logs": len(differences),
                    "estimate_pp": 100 * statistics.mean(differences), "ci_low_pp": 100 * low, "ci_high_pp": 100 * high,
                    "p": permutation_p(differences),
                })
    columns = ["family", "model", "comparison", "logs", "estimate_pp", "ci_low_pp", "ci_high_pp", "p"]
    table = pd.DataFrame(rows, columns=columns)
    primary = table.family == "primary"
    table["p_holm"] = float("nan")
    table.loc[primary, "p_holm"] = holm(table.loc[primary, "p"].tolist())
    return table


def bucket_excess(df: pd.DataFrame) -> pd.DataFrame:
    """Each failure bucket's share of calls per version, and how much more often (percentage points)
    it turns up in R, RG, and E than in C, and in R than in E."""
    done = collected(df)
    failures = [b for b in BUCKETS if b != "correct"]
    rows = []
    for (model, instruction), group in done.groupby(["model", "instruction"]):
        rates = pd.crosstab(group.version, group.bucket, normalize="index").reindex(columns=failures, fill_value=0.0)
        for bucket in failures:
            row = {"model": model, "instruction": instruction, "bucket": bucket}
            row.update({v: rates.at[v, bucket] for v in VERSIONS if v in rates.index})
            for left, right in EXCESS:
                if left in rates.index and right in rates.index:
                    row[f"{left} - {right} (pp)"] = 100 * (rates.at[left, bucket] - rates.at[right, bucket])
            rows.append(row)
    return pd.DataFrame(rows)


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
            "wrong_values": " ".join("-" if pd.isna(v) else f"{v:g}" for v in wrong),  # - is a gave-up or cut-off
            # the same wrong number every time is a systematic mistake; different ones, losing track
            "same_wrong_every_time": bool(pattern == "never" and len(group) > 1 and wrong.notna().all() and wrong.nunique() == 1),
        })
    return pd.DataFrame(rows)


def consistency_summary(consistency: pd.DataFrame) -> pd.DataFrame:
    table = pd.crosstab([consistency.model, consistency.instruction, consistency.version], consistency.pattern)
    table = table.reindex(columns=["always", "sometimes", "never"], fill_value=0)
    table["never_same_wrong"] = consistency.groupby(CELL).same_wrong_every_time.sum()
    return _in_version_order(table.reset_index())


def bootstrap(values: list[float]) -> tuple[float, float]:
    """95% percentile interval of the mean, resampling logs."""
    rng = random.Random(SEED)
    draws = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(BOOTSTRAP_DRAWS))
    return draws[round(0.025 * (BOOTSTRAP_DRAWS - 1))], draws[round(0.975 * (BOOTSTRAP_DRAWS - 1))]


def permutation_p(values: list[float]) -> float:
    """Two-sided paired permutation test: with no effect, each log's difference is as likely to have either sign."""
    observed = abs(statistics.mean(values))
    if observed == 0:
        return 1.0
    rng = random.Random(SEED)
    extreme = sum(
        abs(sum(v if rng.random() < 0.5 else -v for v in values)) / len(values) >= observed - 1e-12
        for _ in range(PERMUTATIONS)
    )
    return (extreme + 1) / (PERMUTATIONS + 1)


def holm(pvalues: list[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values."""
    order = sorted(range(len(pvalues)), key=pvalues.__getitem__)
    adjusted, running = [0.0] * len(pvalues), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(pvalues) - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


def analyze(run: Run) -> str:
    """Write the tables to <run>/analysis/ and return a text report."""
    df = scored_frame(run)
    tables = {"scored": df}
    lines = [f"{run.path.name}: {int(df.collected.sum())} of {len(df)} planned calls collected"]
    if df.collected.any():
        tables.update(accuracy=accuracy_table(df), comparisons=comparison_table(df), bucket_excess=bucket_excess(df))
        accuracy, comparisons = tables["accuracy"], tables["comparisons"]
        primary = comparisons[comparisons.family == "primary"].drop(columns="family")
        exploratory = comparisons[comparisons.family == "exploratory"].drop(columns=["family", "p_holm"])
        lines += _section("Accuracy and buckets", accuracy.drop(columns=["mean_input_tokens", "mean_output_tokens"]))
        lines += _section("Primary comparisons (repeats averaged per log; 95% bootstrap CI; Holm-corrected p)", primary)
        lines += _section("Exploratory comparisons (uncorrected)", exploratory)
        excess = tables["bucket_excess"]
        shown = excess[excess[[v for v in VERSIONS if v in excess]].sum(axis=1) > 0]  # the CSV keeps every bucket
        lines += _section("Failure buckets that occurred: share of calls per version, and excess over the baselines", shown)
        if run.config.repeats > 1:
            tables["consistency"] = consistency_table(df)
            tables["consistency_summary"] = consistency_summary(tables["consistency"])
            lines += _section("Consistency across repeats, exploratory (logs per pattern)", tables["consistency_summary"])
        lines += _section("Tokens", accuracy[[*CELL, "mean_input_tokens", "mean_output_tokens"]])
        lines += _notes(collected(df))
    out = run.path / "analysis"
    out.mkdir(exist_ok=True)
    for name, table in tables.items():
        table.to_csv(out / f"{name}.csv", index=False)
    report = "\n".join(lines)
    (out / "report.txt").write_text(report + "\n")
    return report


def _notes(done: pd.DataFrame) -> list[str]:
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
    return ["", "Notes:", *(f"  - {note}" for note in notes)] if notes else []


def _in_version_order(table: pd.DataFrame) -> pd.DataFrame:
    return table.sort_values(CELL, key=lambda column: column.map(VERSIONS.index) if column.name == "version" else column, kind="stable")


def _section(title: str, table: pd.DataFrame) -> list[str]:
    if table.empty:
        return ["", title, "  (none for the collected calls)"]
    return ["", title, table.to_string(index=False, float_format=lambda x: f"{x:.4g}")]
