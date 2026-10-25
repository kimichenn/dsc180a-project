"""Score every counted call and build the tables a run reports.

Each trial counts its earliest valid attempt (completed, with no harness failure); any later valid
attempt (the same trial collected on two machines) is reported and left out. A trial that failed all
its attempts is left out and reported per cell, and a call flagged for the model's own behaviour (such
as trying a tool) is scored like any other. gave_up and cut_off count as wrong everywhere.

A main run reports, for each model:
- Primary comparisons, on tier 1 (repeats 1-3) only; tier 2's repeats never enter them:
      H1  E - R, no skill                       is it the withdrawal logic, or just the extra numbers?
      H2  skill - no skill on withdrawal logs   per log, the mean of the skill's gain on R and on RG
  A log's accuracy in a cell is the mean of its valid repeats, and a log drops out of a comparison only
  if a cell it needs has no valid call. Each estimate is the mean per-log difference
  in percentage points, with a 95% percentile bootstrap CI over logs and a two-sided sign-flip
  p-value, Holm-corrected across both models' four tests at familywise alpha 0.05 (see stats.py).
- For a cell at 0% or 100% accuracy, the exact one-sided 95% bound on the share of logs with any error.
- Secondary and exploratory comparisons: estimates and CIs only, no tests.
- Error signatures per version, with C and E as the false-match baseline; withdrawal signatures by
  chain depth (exploratory); and each signature's coverage (appendix).
- Repeatability, descriptive only: tier 1 in every cell, and tier 2's repeats on its logs.
A development run (a trial) reports only what checks the setup. It is never evidence.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict
from itertools import combinations

import pandas as pd

from experiment.records import VERSIONS
from experiment.runs import MAX_CALL_ATTEMPTS, Run, counted, counts_toward_cap, left_out, read_attempts
from experiment.scoring import RECORD_SIGNATURES, SIGNATURES, STATUSES, hit_length_limit, index_signatures, match_signatures, score
from experiment.stats import ALPHA, EXACT_MAX_LOGS, RANDOM_FLIPS, bootstrap_ci, holm, one_sided_bound, sign_flip_p

CELL = ["model", "instruction", "version"]
WRONG = [s for s in STATUSES if s != "correct"]
CALLS_TITLE = f"Calls per cell: valid, retried, failed attempts, left out after {MAX_CALL_ATTEMPTS} failures, and model-flagged (scored)"

# A comparison weights each log's accuracy in some (instruction, version) cells and sums them.
Comparison = dict[tuple[str, str], float]


def _versus(left: str, right: str, instruction: str) -> Comparison:
    return {(instruction, left): 1, (instruction, right): -1}


def _skill_gain(version: str, weight: float = 1) -> Comparison:
    return {("skill", version): weight, ("none", version): -weight}


PRIMARY: dict[str, Comparison] = {
    "H1: E - R (no skill)": _versus("E", "R", "none"),
    "H2: skill - no skill on R and RG": {**_skill_gain("R", 0.5), **_skill_gain("RG", 0.5)},
}
SECONDARY: dict[str, Comparison] = {
    "skill - no skill on R": _skill_gain("R"),
    "skill - no skill on RG": _skill_gain("RG"),
    "C - R (no skill)": _versus("C", "R", "none"),
    "C - R (skill)": _versus("C", "R", "skill"),
    "R - RG (no skill)": _versus("R", "RG", "none"),
    "R - RG (skill)": _versus("R", "RG", "skill"),
    "skill - no skill on C": _skill_gain("C"),
    "skill - no skill on E": _skill_gain("E"),
    "skill gain on R - skill gain on E": {**_skill_gain("R"), **_skill_gain("E", -1)},
}


def scored_frame(run: Run) -> pd.DataFrame:
    """One row per planned trial, with its failed attempts; collected ones carry their score, signatures,
    model-behaviour flags, and tokens."""
    attempts = read_attempts(run)
    chosen = counted(attempts)
    valid = Counter(a["trial_id"] for a in attempts if a["status"] == "completed" and a["eligible"])
    failed = Counter(a["trial_id"] for a in attempts if counts_toward_cap(a))
    given_up = left_out(attempts)
    rows = []
    for trial in run.trials:
        attempt = chosen.get(trial.trial_id)
        row = {**asdict(trial), "collected": attempt is not None, "failed_attempts": failed[trial.trial_id],
               "left_out": trial.trial_id in given_up}
        if attempt:
            usage = attempt["usage"]
            limit = run.config.models[trial.model].max_output_tokens
            row.update(_score_columns(score(attempt["response"], run.keys[trial.world_id], hit_length_limit(usage, attempt["stop_reason"], limit))))
            row.update(
                input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"),
                reasoning_output_tokens=usage.get("reasoning_output_tokens"), turns=usage.get("turns"),
                response_chars=len(attempt["response"]), model_flags="; ".join(attempt["model_flags"]), elapsed_s=attempt["elapsed_s"],
                operator=attempt["operator"], client_version=attempt["client_version"], extra_valid_attempts=valid[trial.trial_id] - 1,
                attempt_file=attempt["file"],
            )
        rows.append(row)
    return pd.DataFrame(rows)


def _score_columns(scored: dict) -> dict:
    """A score as flat columns: one boolean per signature, each record signature's number of candidate
    records, and the candidates themselves."""
    matched = scored.pop("signatures")
    columns = {**scored, **{name: name in matched for name in SIGNATURES}}
    columns.update({f"{name}_candidates": len(matched.get(name, [])) for name in RECORD_SIGNATURES})
    columns["signature_records"] = "; ".join(f"{name} {' '.join(map(str, ids))}" for name, ids in matched.items() if ids)
    return columns


def collected(df: pd.DataFrame) -> pd.DataFrame:
    """The collected rows, with `correct` and the signatures as real booleans (they are empty for uncollected rows)."""
    return df[df.collected].astype({"correct": bool, **{name: bool for name in SIGNATURES}})


def attempt_table(df: pd.DataFrame) -> pd.DataFrame:
    """Per cell and tier: planned calls; valid ones, and how many of those needed a retry; failed
    attempts; calls left out after failing every attempt; calls still to collect; and valid calls
    flagged for the model's own behaviour, which are scored like any other."""
    frame = df.assign(retried=df.collected & df.failed_attempts.gt(0), flagged=df.collected & df.model_flags.fillna("").ne(""))
    table = frame.groupby([*CELL, "tier"]).agg(
        planned=("trial_id", "size"), valid=("collected", "sum"), retried=("retried", "sum"),
        failed_attempts=("failed_attempts", "sum"), left_out=("left_out", "sum"), flagged=("flagged", "sum"),
    )
    table["to_collect"] = table.planned - table.valid - table.left_out
    return _in_version_order(table.reset_index())


def accuracy_table(done: pd.DataFrame) -> pd.DataFrame:
    """Accuracy and each wrong status's count per model, instruction, and version."""
    table = done.groupby(CELL).agg(
        logs=("world_id", "nunique"), calls=("correct", "size"), correct=("correct", "sum"),
        mean_output_tokens=("output_tokens", "mean"),
    )
    table.insert(3, "accuracy", table.correct / table.calls)
    statuses = pd.crosstab([done.model, done.instruction, done.version], done.status).reindex(columns=WRONG, fill_value=0)
    return _in_version_order(table.join(statuses).reset_index())


def extreme_cells(done: pd.DataFrame) -> pd.DataFrame:
    """For each cell at 0% or 100% accuracy, the exact one-sided 95% bound on the share of logs with
    any error across their repeats: an upper bound when no log had one, a lower bound when all did."""
    rows = []
    for (model, instruction, version), cell in done.groupby(CELL):
        if cell.correct.all() or not cell.correct.any():
            logs = cell.world_id.nunique()
            with_error = int((~cell.groupby("world_id").correct.all()).sum())
            rows.append({
                "model": model, "instruction": instruction, "version": version, "accuracy": cell.correct.mean(),
                "logs": logs, "logs_with_any_error": with_error, "bound": "upper" if with_error == 0 else "lower",
                "share_of_logs_with_any_error_95_bound": one_sided_bound(with_error, logs),
            })
    return pd.DataFrame(rows, columns=[*CELL, "accuracy", "logs", "logs_with_any_error", "bound", "share_of_logs_with_any_error_95_bound"])


def comparison_table(done: pd.DataFrame) -> pd.DataFrame:
    """Every primary and secondary comparison the collected cells allow, in percentage points."""
    per_log = done.groupby(["model", "world_id", "instruction", "version"]).correct.mean().unstack(["instruction", "version"])
    rows = []
    for model, table in per_log.groupby(level="model"):
        for family, comparisons in (("primary", PRIMARY), ("secondary", SECONDARY)):
            for name, weights in comparisons.items():
                differences = _differences(table, weights)
                if not differences:
                    continue
                low, high = bootstrap_ci(differences)
                rows.append({
                    "family": family, "model": model, "comparison": name, "logs": len(differences),
                    "nonzero_logs": sum(d != 0 for d in differences), "estimate_pp": 100 * sum(differences) / len(differences),
                    "ci_low_pp": 100 * low, "ci_high_pp": 100 * high,
                    "p": sign_flip_p(differences) if family == "primary" else math.nan,
                })
    columns = ["family", "model", "comparison", "logs", "nonzero_logs", "estimate_pp", "ci_low_pp", "ci_high_pp", "p"]
    table = pd.DataFrame(rows, columns=columns)
    primary = table.family == "primary"
    table["p_holm"] = math.nan
    table.loc[primary, "p_holm"] = holm(table.loc[primary, "p"].tolist())
    table["holm_reject"] = table.p_holm.le(ALPHA).where(primary)
    return table


def _differences(per_log: pd.DataFrame, weights: Comparison) -> list[float]:
    """Each log's weighted sum of its cell accuracies, over the logs that have every cell, rounded so
    float noise reads as zero; empty if the run lacks a cell."""
    if any(cell not in per_log.columns for cell in weights):
        return []
    cells = per_log[list(weights)].dropna()
    return [round(value, 12) for value in sum(cells[cell] * weight for cell, weight in weights.items())]


def signature_rates(done: pd.DataFrame) -> pd.DataFrame:
    """Each signature's share of calls per version. C has neither withdrawals nor gossip and E has the
    withdrawals' numbers without their logic, so their rates show how often a signature matches by chance."""
    rows = []
    for (model, instruction), group in done.groupby(["model", "instruction"]):
        by_version = group.groupby("version")[list(SIGNATURES)].mean()
        for name in SIGNATURES:
            rows.append({"model": model, "instruction": instruction, "signature": name,
                         **{v: by_version.at[v, name] for v in VERSIONS if v in by_version.index}})
    return pd.DataFrame(rows)


def depth_table(done: pd.DataFrame, run: Run) -> pd.DataFrame:
    """Exploratory: how often a wrong number matches a withdrawal signature, by the depth of the chain it
    points to and by odd (cancelled) vs. even (restored) depth. A log has many more shallow chains than
    deep ones, so the rate is per chain: matches over calls x chains of that depth in each call's log."""
    chains = {world: Counter(c["depth"] for c in key["chains"]) for world, key in run.keys.items()}
    rows = []
    for (model, instruction, version), cell in done.groupby(CELL):
        matched = Counter(int(d) for d in cell.chain_depth.dropna())
        chances = sum((chains[world] for world in cell.world_id), Counter())
        groups = {f"depth {d}": [d] for d in sorted(chances)}
        groups["odd depth (cancelled)"] = [d for d in chances if d % 2]
        groups["even depth (restored)"] = [d for d in chances if not d % 2]
        for label, depths in groups.items():
            hits, tries = sum(matched[d] for d in depths), sum(chances[d] for d in depths)
            rows.append({"model": model, "instruction": instruction, "version": version, "chains": label,
                         "matches": hits, "chain_calls": tries, "rate_per_chain": hits / tries if tries else math.nan})
    return pd.DataFrame(rows)


def coverage_table(run: Run) -> pd.DataFrame:
    """Appendix: each signature's coverage of a log, the share of signed errors in the plausible range
    that its values cover. The plausible range is every nonzero whole-$K error that keeps the answer
    within the budget range. Coverage is how much of that range a signature takes up, not a probability."""
    low, high = run.config.generator.budget_min, run.config.generator.budget_max
    per_log = []
    for key in run.keys.values():
        index = index_signatures(key["signatures"])
        errors = [e for e in range(low - key["answer"], high - key["answer"] + 1) if e]
        hits = Counter(name for error in errors for name in match_signatures(error, index)[0])
        per_log.append({name: hits[name] / len(errors) for name in SIGNATURES})
    table = pd.DataFrame(per_log, columns=list(SIGNATURES))
    summary = pd.DataFrame({"mean_coverage": table.mean(), "min_coverage": table.min(), "max_coverage": table.max()})
    return summary.rename_axis("signature").reset_index()


def repeatability(planned: pd.DataFrame, repeats: int) -> pd.DataFrame:
    """Per cell, over logs whose `repeats` repeats were all collected (the others are counted as left
    out): how many logs got each number of repeats right; exact-answer agreement, the share of pairs of
    a log's repeats that gave the same number (a gave_up or cut_off has none, so its pairs never agree
    and are counted on their own); and always-wrong logs that gave the same wrong number every time."""
    rows = []
    for (model, instruction, version), cell in planned.groupby(CELL):
        logs = [log for _, log in cell.groupby("world_id") if len(log) == repeats and log.collected.all()]
        right = Counter(int(log.correct.astype(bool).sum()) for log in logs)
        pairs = same = no_number = always_wrong = same_wrong = 0
        for log in logs:
            numbers = [v if s in ("correct", "wrong_number") else None for v, s in zip(log.value, log.status)]
            for a, b in combinations(numbers, 2):
                pairs += 1
                no_number += a is None or b is None
                same += a is not None and a == b
            if not log.correct.astype(bool).any():
                always_wrong += 1
                same_wrong += numbers[0] is not None and len(set(numbers)) == 1
        rows.append({
            "model": model, "instruction": instruction, "version": version, "logs": len(logs),
            "left_out": cell.world_id.nunique() - len(logs), **{f"right_{k}": right[k] for k in range(repeats + 1)},
            "pairs": pairs, "same_number_pairs": same, "agreement": same / pairs if pairs else math.nan,
            "pairs_with_no_number": no_number, "always_wrong": always_wrong, "always_same_wrong_number": same_wrong,
        })
    return _in_version_order(pd.DataFrame(rows))


def tier2_planned(df: pd.DataFrame, run: Run) -> pd.DataFrame:
    """Every planned call in a tier-2 cell on a tier-2 log, tier 1's repeats included."""
    t2 = run.config.tier2
    logs = set(df.loc[df.tier == 2, "world_id"])
    return df[df.world_id.isin(logs) & df.version.isin(t2.versions) & df.instruction.isin(t2.instructions)]


def session_check(run: Run, attempts: list[dict]) -> pd.DataFrame:
    """From each valid call's saved metadata: every call ran in a session of its own, and every call to
    a model used one model id and one effort, and was served that model."""
    calls = list(counted(attempts).values())
    uses = Counter(a.get("session_id") for a in calls)
    rows = []
    for model in run.config.models:
        mine = [a for a in calls if a["model"] == model]
        served = {a["served_model"] for a in mine} - {None}
        row = {
            "model": model, "calls": len(mine), "missing_session_ids": sum(not a.get("session_id") for a in mine),
            "shared_session_ids": sum(uses[a["session_id"]] > 1 for a in mine if a.get("session_id")),
            "model_ids": " ".join(sorted({a["model_id"] for a in mine})), "efforts": " ".join(sorted({a["effort"] for a in mine})),
            "served_models": " ".join(sorted(served)) or "-",
        }
        row["ok"] = (not row["missing_session_ids"] and not row["shared_session_ids"] and len({a["model_id"] for a in mine}) == 1
                     and len({a["effort"] for a in mine}) == 1 and served <= {a["model_id"] for a in mine})
        rows.append(row)
    return pd.DataFrame(rows)


def repeat_answers(planned: pd.DataFrame) -> pd.DataFrame:
    """Per log in each tier-2 cell: its answers in repeat order (- for gave_up or cut_off), and whether they vary."""
    rows = []
    for (model, instruction, version, world), log in collected(planned).groupby([*CELL, "world_id"]):
        log = log.sort_values("repeat")
        answers = ["-" if pd.isna(v) else f"{v:g}" for v in log.value]
        rows.append({"model": model, "instruction": instruction, "version": version, "world_id": world,
                     "repeats": len(log), "correct": int(log.correct.sum()), "answers": " ".join(answers),
                     "varies": len(set(answers)) > 1})
    return pd.DataFrame(rows)


def analyze(run: Run) -> str:
    """Write the tables to <run>/analysis/ and return a text report."""
    df = scored_frame(run)
    tables = {"scored": df}
    lines = [f"{run.path.name}: {int(df.collected.sum())} of {len(df)} planned calls collected"]
    if df.collected.any():
        build = _main_report if run.config.purpose == "main" else _development_report
        more, sections = build(run, df)
        tables.update(more)
        lines += sections + _notes(df)
    out = run.path / "analysis"
    out.mkdir(exist_ok=True)
    for name, table in tables.items():
        table.to_csv(out / f"{name}.csv", index=False)
    report = "\n".join(lines)
    (out / "report.txt").write_text(report + "\n")
    return report


def _main_report(run: Run, df: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Every table the design reports, and the text sections that show them."""
    done = collected(df)
    tier1 = done[done.tier == 1]
    tables = {
        "calls": attempt_table(df), "accuracy": accuracy_table(tier1), "extreme_cells": extreme_cells(tier1),
        "comparisons": comparison_table(tier1),
        "signature_rates": signature_rates(tier1), "signature_depth": depth_table(tier1, run),
        "repeatability_tier1": repeatability(df[df.tier == 1], run.config.tier1.repeats),
        "repeatability_tier2": repeatability(tier2_planned(df, run), run.config.tier2.repeats),
        "signature_coverage": coverage_table(run),
    }
    comparisons = tables["comparisons"]
    primary = comparisons[comparisons.family == "primary"].drop(columns="family")
    secondary = comparisons[comparisons.family == "secondary"].drop(columns=["family", "p", "p_holm", "holm_reject"])
    depth = tables["signature_depth"].pivot_table(index=["model", "instruction", "chains"], columns="version", values="rate_per_chain", sort=False)
    sections = _section(CALLS_TITLE, tables["calls"])
    sections += _section("Accuracy, tier 1 (repeats 1-3); gave_up and cut_off count as wrong", tables["accuracy"])
    sections += _section(
        "Primary comparisons, tier 1 (mean per-log difference; 95% bootstrap CI over logs; Holm-corrected p)", primary,
        f"Sign-flip p-values assume each log's difference is symmetric about zero under no effect. They are exact over "
        f"every sign pattern when at most {EXACT_MAX_LOGS} logs differ, else from {RANDOM_FLIPS:,} random flips. "
        f"Holm across both models' tests, familywise alpha {ALPHA}.",
    )
    sections += _section("Cells at 0% or 100% accuracy: exact one-sided 95% bound on the share of logs with any error across their repeats",
                         tables["extreme_cells"])
    sections += _section("Secondary and exploratory comparisons, tier 1 (estimates and 95% CIs, no tests)", secondary)
    sections += _section("Error signatures, exploratory: share of calls per version (C and E are the false-match baseline)",
                         tables["signature_rates"])
    sections += _section("Withdrawal signatures by chain depth, exploratory: matches per chain per call", depth.reset_index())
    sections += _section("Repeatability, tier 1, descriptive (logs by repeats right; exact-answer agreement)", tables["repeatability_tier1"])
    sections += _section("Repeatability, tier 2, descriptive (each log's correct answers out of all its repeats; logs with every repeat only)",
                         tables["repeatability_tier2"])
    sections += _section("Appendix: signature coverage (share of plausible signed errors each signature covers; not a probability)",
                         tables["signature_coverage"])
    return tables, sections


def _development_report(run: Run, df: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """A trial's checks of the setup: accuracy and output length per cell, whether repeats vary, and sessions."""
    done = collected(df)
    accuracy = done[done.tier == 1].groupby(CELL).agg(
        calls=("correct", "size"), correct=("correct", "sum"), hit_length_limit=("hit_length_limit", "sum"),
        mean_output_tokens=("output_tokens", "mean"), max_output_tokens=("output_tokens", "max"),
        mean_response_chars=("response_chars", "mean"),
    )
    accuracy.insert(2, "accuracy", accuracy.correct / accuracy.calls)
    tables = {
        "calls": attempt_table(df),
        "accuracy": _in_version_order(accuracy.reset_index()),
        "repeats": repeat_answers(tier2_planned(df, run)),
        "sessions": session_check(run, read_attempts(run)),
    }
    sections = ["DEVELOPMENT RUN: it checks the setup only. Never analyze it as evidence or pool it with the main run."]
    sections += _section(CALLS_TITLE, tables["calls"])
    sections += _section("Accuracy and output length per cell, tier 1", tables["accuracy"])
    sections += _section("Repeats of the tier-2 logs: answers in repeat order, and whether they vary", tables["repeats"])
    sections += _section("Sessions and settings from saved call metadata (ok: a new session per call, one model id and effort)",
                         tables["sessions"])
    return tables, sections


def _notes(df: pd.DataFrame) -> list[str]:
    done = collected(df)
    notes = []
    extra = int(done.extra_valid_attempts.sum())
    if extra:
        notes.append(f"{extra} extra valid attempts left out (a trial collected more than once; the earliest counts)")
    given_up = int(df.left_out.sum())
    if given_up:
        notes.append(f"{given_up} calls failed all {MAX_CALL_ATTEMPTS} attempts and are left out")
    flagged = int(done.model_flags.ne("").sum())
    if flagged:
        notes.append(f"{flagged} valid calls are flagged for the model's own behaviour (such as trying a tool); they are scored like any other")
    limited = done[done.hit_length_limit]
    if len(limited):
        notes.append(f"{len(limited)} responses hit the output limit (hit_length_limit): {int((limited.status == 'cut_off').sum())} "
                     "had no ANSWER line (cut_off); the rest are scored on their final ANSWER line")
    for model, versions in done.groupby("model").client_version.unique().items():
        if len(versions) > 1:
            notes.append(f"{model} was collected with several CLI versions: {', '.join(sorted(versions))}")
    return ["", "Notes:", *(f"  - {note}" for note in notes)] if notes else []


def _in_version_order(table: pd.DataFrame) -> pd.DataFrame:
    if table.empty:
        return table
    return table.sort_values(CELL, key=lambda column: column.map(VERSIONS.index) if column.name == "version" else column, kind="stable")


def _section(title: str, table: pd.DataFrame, note: str = "") -> list[str]:
    body = ["  (none for the collected calls)"] if table.empty else [table.to_string(index=False, float_format=lambda x: f"{x:.4g}")]
    return ["", title, *body, *([f"  {note}"] if note else [])]
