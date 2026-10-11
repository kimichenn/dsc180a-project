"""Measures, hypothesis tables, and the stage decision rules, computed from labeled responses.

Repeated generations are not independent items, so every comparison first collapses
them into one score per scenario cell (the share of generations labeled correct).
"""

from __future__ import annotations

from math import ceil, floor

import pandas as pd

from conflict_eval.prompts import DISTANCES, INSTRUCTION_LEVELS, MAX_RUNG, RULE_PLACEMENTS, VARIANTS
from conflict_eval.scenarios import FORMATS, QUESTION_TYPES, SUBTYPES

ORDER = {
    "variant": VARIANTS,
    "question_type": QUESTION_TYPES,
    "distance": DISTANCES,
    "rule_placement": RULE_PLACEMENTS,
    "instruction": INSTRUCTION_LEVELS,
    "conflict_subtype": SUBTYPES,
    "format": FORMATS,
}
CELL = [
    "model", "scenario_id", "conflict_subtype", "format", "domain",
    "variant", "question_type", "distance", "rule_placement", "instruction", "rung",
]
SETTING = ["question_type", "distance", "rule_placement"]


def to_frame(scored_rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(scored_rows)
    for column, levels in ORDER.items():
        df[column] = pd.Categorical(df[column], categories=levels, ordered=True)
    return df


def collapse(df: pd.DataFrame) -> pd.DataFrame:
    """One row per model x scenario x condition."""
    labeled = df[df["label"].notna()]
    flags = labeled.assign(
        correct=labeled["label"].eq("correct"),
        adopted=labeled["label"].eq("adopted_nongoverning"),
        no_answer=labeled["label"].eq("no_answer"),
        mentions=labeled["mentions_conflict"].astype(bool),
    )
    cells = flags.groupby(CELL, observed=True).agg(
        score=("correct", "mean"),
        adopted=("adopted", "mean"),
        no_answer=("no_answer", "mean"),
        mentions=("mentions", "mean"),
        generations=("label", "size"),
        distinct_labels=("label", "nunique"),
    )
    cells = cells.reset_index()
    cells["majority_correct"] = cells["score"] > 0.5
    return cells


def fraction(correct: float, total: int) -> str:
    """'7/8'; scores averaged over generations can make the numerator fractional ('6.67/8')."""
    return f"{round(correct, 2):g}/{total}"


def count_table(cells: pd.DataFrame, rows: list[str], columns: list[str]) -> pd.DataFrame:
    """'correct/scenarios' for each combination, e.g. the six-condition table."""
    grouped = cells.groupby(rows + columns, observed=True)["score"].agg(["sum", "size"])
    text = pd.Series([fraction(s, n) for s, n in zip(grouped["sum"], grouped["size"])], index=grouped.index)
    return text.unstack(columns).fillna("")


def rate_table(cells: pd.DataFrame, rows: list[str], columns: list[str], value: str) -> pd.DataFrame:
    rates = cells.groupby(rows + columns, observed=True)[value].mean()
    return rates.map(lambda r: f"{r:.0%}").unstack(columns).fillna("")


def paired(cells: pd.DataFrame, factor: str, base: str, treatment: str) -> pd.DataFrame:
    """Per-scenario score difference (treatment - base), all other factors matched."""
    keys = [c for c in CELL if c != factor]
    a = cells[cells[factor] == base].set_index(keys)["score"]
    b = cells[cells[factor] == treatment].set_index(keys)["score"]
    pairs = pd.concat({base: a, treatment: b}, axis=1, join="inner").reset_index()
    pairs["diff"] = pairs[treatment] - pairs[base]
    return pairs


def compare(cells: pd.DataFrame, factor: str, base: str, treatment: str, by: list[str]) -> pd.DataFrame:
    pairs = paired(cells, factor, base, treatment)
    rows = []
    for key, group in pairs.groupby(by, observed=True):
        key = key if isinstance(key, tuple) else (key,)
        n = len(group)
        rows.append({
            **dict(zip(by, key)),
            base: fraction(group[base].sum(), n),
            treatment: fraction(group[treatment].sum(), n),
            "mean diff": round(group["diff"].mean(), 3),
            "worse": int((group["diff"] < 0).sum()),
            "better": int((group["diff"] > 0).sum()),
        })
    return pd.DataFrame(rows).set_index(by) if rows else pd.DataFrame()


def stage0_decision(cells: pd.DataFrame) -> tuple[pd.DataFrame, bool, str]:
    """Go to Stage 1 if some model gets >= 7/8 Consistent right and >= 2/8 matched Conflict wrong."""
    base = cells[cells["instruction"] == "none"]
    n = base["scenario_id"].nunique()
    need_consistent, need_wrong = ceil(7 * n / 8), ceil(2 * n / 8)
    rows = []
    for model, group in base.groupby("model"):
        consistent = group[group["variant"] == "consistent"]
        conflict = group[group["variant"] == "conflict"]
        consistent_correct = int(consistent["majority_correct"].sum())
        conflict_wrong = int((~conflict["majority_correct"]).sum())
        solved = set(consistent.loc[consistent["majority_correct"], "scenario_id"])
        conflict_only = int((~conflict.loc[conflict["scenario_id"].isin(solved), "majority_correct"]).sum())
        rows.append({
            "model": model,
            "consistent correct": f"{consistent_correct}/{len(consistent)}",
            "conflict wrong": f"{conflict_wrong}/{len(conflict)}",
            "wrong only under conflict": conflict_only,
            "qualifies": consistent_correct >= need_consistent and conflict_wrong >= need_wrong,
        })
    table = pd.DataFrame(rows).set_index("model")
    rule = f"needs >= {need_consistent}/{n} Consistent correct and >= {need_wrong}/{n} Conflict wrong (majority of generations)"
    return table, bool(table["qualifies"].any()), rule


def stage1_selection(cells: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, bool]:
    """Apply the pre-registered rule for choosing the single Stage 2 setting."""
    base = cells[cells["instruction"] == "none"]
    n = base["scenario_id"].nunique()
    models = sorted(base["model"].unique())
    need_consistent = ceil(11 * n / 12)
    low, high, target = ceil(6 * n / 12), floor(10 * n / 12), 8 * n / 12
    rows = []
    for setting, group in base.groupby(SETTING, observed=True):
        consistent = group[group["variant"] == "consistent"].groupby("model")["score"].sum()
        conflict = group[group["variant"] == "conflict"].groupby("model")["score"].sum()
        conflict_scores = [conflict.get(m, 0) for m in models]
        row = dict(zip(SETTING, setting))
        for m in models:
            row[f"{m} consistent"] = fraction(consistent.get(m, 0), n)
            row[f"{m} conflict"] = fraction(conflict.get(m, 0), n)
        row["step 1"] = all(consistent.get(m, 0) >= need_consistent for m in models)
        row["step 2"] = row["step 1"] and sum(low <= s <= high for s in conflict_scores) >= min(2, len(models))
        row["median conflict"] = float(pd.Series(conflict_scores).median())
        row["conflict errors"] = float((1 - group.loc[group["variant"] == "conflict", "score"]).sum())
        rows.append(row)
    table = pd.DataFrame(rows)
    passing = table[table["step 2"]]
    if len(passing):
        chosen = passing.loc[(passing["median conflict"] - target).abs().idxmin()]
        return table, chosen, False
    return table, table.loc[table["conflict errors"].idxmax()], True


def build_report(df: pd.DataFrame, manifest: dict) -> tuple[str, dict[str, pd.DataFrame]]:
    """Printable report, plus the per-scenario tables worth saving."""
    out: list[str] = []
    tables: dict[str, pd.DataFrame] = {}

    def section(title: str, body) -> None:
        text = body if isinstance(body, str) else body.to_string()
        out.extend([f"== {title} ==", text, ""])

    pending = int(df["label"].isna().sum())
    sources = df["label_source"].value_counts()
    coverage = (
        f"responses: {len(df)}  |  auto-labeled: {sources.get('auto', 0)}  |  hand-labeled: {sources.get('hand', 0)}"
        f"  |  pending review: {pending}"
    )
    if pending:
        coverage += "\nPending responses are left out below. Label them first: python -m conflict_eval label <run dir>"
    section("Coverage", coverage)

    cells = collapse(df)
    if cells.empty:
        return "\n".join(out), tables
    tables["scenario_results"] = cells
    present = {f: list(cells[f].unique()) for f in ORDER}

    section("Accuracy: correct / scenarios", count_table(cells, ["model", "variant"], ["instruction"]))
    conflict = cells[cells["variant"] == "conflict"]
    consistent = cells[cells["variant"] == "consistent"]
    if len(conflict):
        section("Adoption rate (conflict responses that used the non-governing claim)",
                rate_table(conflict, ["model"], ["instruction"], "adopted"))
    section("Mentions the conflict", rate_table(cells, ["model", "variant"], ["instruction"], "mentions"))

    if set(VARIANTS) <= set(present["variant"]):
        tables["conflict_drop"] = paired(cells, "variant", "consistent", "conflict")
        uninstructed = cells[cells["instruction"] == "none"]
        note = "Conflict drop = conflict - consistent per scenario (negative = worse under conflict), no extra instruction."
        section("H1: conflict drop by question type", f"{note}\n{compare(uninstructed, 'variant', 'consistent', 'conflict', ['model', 'question_type']).to_string()}")
        for factor in ("distance", "rule_placement", "format"):
            if len(present[factor]) > 1:
                section(f"Conflict drop by {factor}", compare(uninstructed, "variant", "consistent", "conflict", ["model", factor]))
        section("H4: conflict drop by subtype",
                compare(uninstructed, "variant", "consistent", "conflict", ["model", "conflict_subtype"]))
        section("H4: adoption rate by subtype",
                rate_table(conflict[conflict["instruction"] == "none"], ["model"], ["conflict_subtype"], "adopted"))

    if {"none", "skill"} <= set(present["instruction"]):
        tables["skill_recovery"] = paired(conflict, "instruction", "none", "skill")
        section("H2: skill recovery (conflict + skill - conflict)", compare(conflict, "instruction", "none", "skill", ["model"]))
        if "warning" in present["instruction"]:
            section("H2: skill vs one-line warning (conflict)", compare(conflict, "instruction", "warning", "skill", ["model"]))
            section("Warning vs nothing (conflict)", compare(conflict, "instruction", "none", "warning", ["model"]))
        section("H3: skill effect on Consistent accuracy", compare(consistent, "instruction", "none", "skill", ["model"]))
        section("H3: no committed answer, Consistent", rate_table(consistent, ["model"], ["instruction"], "no_answer"))

    stage = manifest.get("design", {}).get("stage")
    if stage == "stage0":
        table, go, rule = stage0_decision(cells)
        if go:
            verdict = "GO to Stage 1 at this rung."
        elif manifest["design"]["rung"] < MAX_RUNG:
            verdict = "No qualifying model: climb one rung and rerun the probe."
        else:
            verdict = "No qualifying model and every rung is exhausted: report the ceiling result."
        section("Stage 0 decision", f"{rule}\n{table.to_string()}\n\n{verdict}")
        disagree = cells[cells["distinct_labels"] > 1]
        if len(disagree):
            section("Generations disagree (read all of them in failures.md)",
                    disagree[["model", "scenario_id", "variant", "score"]].to_string(index=False))
    elif stage == "stage1":
        table, chosen, fallback = stage1_selection(cells)
        rung = manifest["design"]["rung"]
        how = "No setting passed step 2; using the one with the most Conflict errors (say so in the write-up)." if fallback else "Chosen by steps 1-3."
        command = (
            f"python -m conflict_eval run stage2 --rung {rung} --question {chosen['question_type']}"
            f" --distance {chosen['distance']} --rule {chosen['rule_placement']}"
        )
        section("Stage 2 setting", f"{table.to_string(index=False)}\n\n{how}\nNext: {command}")
    return "\n".join(out), tables


def failures_markdown(df: pd.DataFrame) -> str:
    """Every labeled non-correct response, plus cells whose generations disagree, for a read-through."""
    lines = ["# Failure read-through", ""]
    labeled = df[df["label"].notna()].copy()
    labeled["cell"] = labeled[CELL].astype(str).agg("|".join, axis=1)
    disagreeing = set(labeled.groupby("cell")["label"].nunique().loc[lambda s: s > 1].index)
    shown = labeled[(labeled["label"] != "correct") | labeled["cell"].isin(disagreeing)]
    if shown.empty:
        return "\n".join(lines + ["No failures."]) + "\n"
    shown = shown.sort_values(["model", "scenario_id", "variant", "question_type", "distance", "instruction", "generation"])
    for (model, scenario_id), group in shown.groupby(["model", "scenario_id"], sort=False):
        lines += [f"## {model} / {scenario_id}", ""]
        for _, r in group.iterrows():
            flag = " (generations disagree)" if r["cell"] in disagreeing else ""
            lines.append(
                f"- **{r['label']}**{flag}: {r['variant']}, {r['question_type']}, distance={r['distance']}, "
                f"rule={r['rule_placement']}, instruction={r['instruction']}, rung {r['rung']}, gen {r['generation']}"
            )
            lines.append(f"  - Q: {r['question']}  |  expected: {', '.join(r['expected'])}  |  alternative: {', '.join(r['alternative'])}")
            response = (r["response"] or "").strip().replace("\n", "\n  > ")
            lines += [f"  > {response}", ""]
    return "\n".join(lines) + "\n"
