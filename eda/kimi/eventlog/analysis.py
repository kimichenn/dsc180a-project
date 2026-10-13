"""Measures and stage decision rules for v4. Fresh logs are the unit of replication: rates are averaged over logs."""

from __future__ import annotations

import pandas as pd

from eventlog.dials import LOWEST, STAGE_A_STEPS, Dials, stage_settings
from eventlog.generator import TRAP_TYPES
from eventlog.scoring import parse_answer, score_call

PASS_CONSISTENT = 0.03  # a model passes Consistent at <= 3% entity error
GAP = 0.05  # a gap is visible at >= 5 points of Conflict over Consistent
DEFAULT_MODELS_CONFIG = "config/v4_models.toml"


def score_frame(rows: list[dict], log_files: dict[str, dict]) -> pd.DataFrame:
    records = []
    for row in rows:
        meta = log_files[row["log_id"]]
        names = parse_answer(row["response"])
        record = {
            "model": row["model"],
            "setting": row["setting"],
            "seed": row["seed"],
            "version": row["version"],
            "instruction": row["instruction"],
            "n_projects": meta["dials"]["n_projects"],
            "format_failure": names is None,
            "attempts": row.get("attempts", 1),
            "response_chars": len(row["response"] or ""),
            "input_tokens": row.get("input_tokens", 0),
            "output_tokens": row.get("output_tokens", 0),
        }
        if names is not None:
            record.update(score_call(names, meta))
        records.append(record)
    return pd.DataFrame(records)


def pct(x: float) -> str:
    return "" if pd.isna(x) else f"{100 * x:.1f}%"


VERSIONS = ("consistent", "conflict")
INSTRUCTION_ORDER = ("none", "warning", "skill")


def _ordered(table: pd.DataFrame) -> pd.DataFrame:
    """Columns in the proposal's order: Consistent before Conflict, then none / warning / skill."""
    def rank(column):
        parts = column if isinstance(column, tuple) else (column,)
        return [VERSIONS.index(p) if p in VERSIONS else INSTRUCTION_ORDER.index(p) if p in INSTRUCTION_ORDER else 0 for p in parts]
    return table[sorted(table.columns, key=rank)]


def error_table(ok: pd.DataFrame) -> pd.DataFrame:
    """Mean entity error rate over logs."""
    table = ok.pivot_table(index=["setting", "model"], columns=["version", "instruction"], values="error_rate", aggfunc="mean")
    return _ordered(table).map(pct)


def conflict_effects(ok: pd.DataFrame) -> pd.DataFrame:
    """Conflict minus Consistent error, paired by log seed, then averaged."""
    wide = ok.pivot_table(index=["setting", "model", "instruction", "seed"], columns="version", values="error_rate")
    if not {"consistent", "conflict"} <= set(wide.columns):
        return pd.DataFrame()
    wide = wide.dropna(subset=["consistent", "conflict"])
    return (wide["conflict"] - wide["consistent"]).groupby(level=["setting", "model", "instruction"]).mean().rename("effect").reset_index()


def adoption_table(ok: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Share of single-trap projects decided in the trap's direction, by trap type (Conflict logs)."""
    conflict = ok[ok["version"] == "conflict"]
    rows = []
    for key, group in conflict.groupby(by):
        row = dict(zip(by, key if isinstance(key, tuple) else (key,)))
        for kind in TRAP_TYPES:
            wrong, n = group[f"single_{kind}_wrong"].sum(), group[f"single_{kind}_n"].sum()
            row[kind] = f"{int(wrong)}/{int(n)} ({pct(wrong / n)})" if n else ""
        trapped_wrong, trapped_n = group["trapped_wrong"].sum(), group["trapped_n"].sum()
        row["all trapped"] = f"{int(trapped_wrong)}/{int(trapped_n)} ({pct(trapped_wrong / trapped_n)})" if trapped_n else ""
        rows.append(row)
    return pd.DataFrame(rows).set_index(by) if rows else pd.DataFrame()


def spillover_table(ok: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Error on projects with no traps, Conflict vs Consistent."""
    sums = ok.groupby(by + ["version"])[["untrapped_wrong", "untrapped_n"]].sum()
    rates = (sums["untrapped_wrong"] / sums["untrapped_n"]).unstack("version")
    return _ordered(rates).map(pct)


def other_errors_table(df: pd.DataFrame) -> pd.DataFrame:
    ok = df[~df["format_failure"]]
    table = ok.groupby(["model", "version", "instruction"]).agg(
        calls=("exact", "size"), exact=("exact", "sum"), out_of_program=("out_of_program", "sum"), invented=("invented", "sum")
    )
    failures = df.groupby(["model", "version", "instruction"])["format_failure"].sum().rename("format_failures")
    lengths = df.groupby(["model", "version", "instruction"])["response_chars"].median().rename("median chars")
    return table.join(failures, how="outer").join(lengths, how="outer").fillna(0).astype(int)


def model_summary(ok: pd.DataFrame, setting: str, consistent_setting: str | None = None) -> pd.DataFrame:
    """Per model: mean Consistent and Conflict error, pass/gap flags (no extra instruction)."""
    plain = ok[ok["instruction"] == "none"]
    conflict = plain[(plain["setting"] == setting) & (plain["version"] == "conflict")].groupby("model")["error_rate"].mean()
    consistent_rows = plain[(plain["setting"] == (consistent_setting or setting)) & (plain["version"] == "consistent")]
    consistent = consistent_rows.groupby("model")["error_rate"].mean()
    table = pd.DataFrame({"consistent": consistent, "conflict": conflict})
    table["effect"] = table["conflict"] - table["consistent"]
    table["passes consistent"] = table["consistent"] <= PASS_CONSISTENT
    table["gap"] = table["effect"] >= GAP
    return table


def command_flags(manifest: dict, overrides: dict | None = None) -> str:
    parts = [f"--step {manifest['step']}"]
    merged = {**manifest.get("overrides", {}), **(overrides or {})}
    if merged:
        parts.append("--set " + " ".join(f"{k}={v}" for k, v in merged.items()))
    if manifest.get("models_config", DEFAULT_MODELS_CONFIG) != DEFAULT_MODELS_CONFIG:
        parts.append(f"--models-config {manifest['models_config']}")
    if manifest.get("response_format", "working") != "working":
        parts.append(f"--response-format {manifest['response_format']}")
    return " ".join(parts)


def stage_a_decision(ok: pd.DataFrame, manifest: dict) -> str:
    table = model_summary(ok, "main")
    passes, gaps = int(table["passes consistent"].sum()), int(table["gap"].sum())
    shown = table.assign(**{c: table[c].map(pct) for c in ("consistent", "conflict", "effect")})
    lines = [f"Pass Consistent: mean entity error <= {pct(PASS_CONSISTENT)}. Gap: Conflict >= Consistent + {GAP * 100:.0f} points.", shown.to_string(), ""]
    step = manifest["step"]
    if passes >= 2 and gaps >= 1:
        lines.append(f"GO to Stage B at these settings:\n  python -m eventlog run B {command_flags(manifest)}")
    elif passes < 2:
        if step + 1 < len(STAGE_A_STEPS):
            change = ", ".join(f"{k}={v}" for k, v in STAGE_A_STEPS[step + 1].items() if STAGE_A_STEPS[step].get(k) != v)
            lines.append(f"Too hard overall (fewer than two models pass Consistent). Lower the next general dial ({change}):")
            lines.append(f"  python -m eventlog run A {command_flags({**manifest, 'step': step + 1})}")
        else:
            lines.append("Too hard overall even at the lowest general step: report that result.")
    else:
        lines.append("At ceiling: models pass Consistent but none shows a gap. Try, in order:")
        lines.append(f"  python -m eventlog run A {command_flags(manifest, {'n_projects': 200})}")
        lines.append(f"  python -m eventlog run A {command_flags({**manifest, 'models_config': 'config/v4_small_models.toml'})}")
        lines.append(f"  python -m eventlog run A {command_flags({**manifest, 'response_format': 'final_only'})}")
        lines.append("If none of these produce a gap, report that frontier models stay robust at this scale.")
    return "\n".join(lines)


def stage_b_selection(ok: pd.DataFrame, manifest: dict) -> str:
    base = Dials(**manifest["dials"])
    # "At least two models pass Consistent" counts only the models run; Stage B may skip models
    # that were already perfect at Stage A's harder setting.
    need = min(2, ok["model"].nunique())
    rows, eligible = [], {}
    for setting in stage_settings("B", base):
        if setting.label not in set(ok["setting"]):
            continue
        baseline = setting.label if "consistent" in setting.versions else f"n{base.n_projects}"
        table = model_summary(ok, setting.label, baseline)
        passing = table[table["passes consistent"]]
        median = passing["effect"].median() if len(passing) else float("nan")
        rows.append({"setting": setting.label, "models passing": len(passing), "median effect (passing)": pct(median),
                     **{f"{m} effect": pct(e) for m, e in table["effect"].items()}})
        if len(passing) >= need and not pd.isna(median):
            eligible[setting.label] = (median, passing["effect"].mean())
    lines = [pd.DataFrame(rows).to_string(index=False), ""]
    if not eligible:
        lines.append("No Stage B setting has enough models passing Consistent, so the rule picks nothing.")
        return "\n".join(lines)
    # The protocol's rule is the largest median; ties (e.g. two models at zero effect everywhere)
    # are broken by the mean effect of the passing models.
    chosen = max(eligible, key=eligible.get)
    if sum(1 for value in eligible.values() if value[0] == eligible[chosen][0]) > 1:
        lines.append(f"Median effect ties at {pct(eligible[chosen][0])}; broken by the mean effect of passing models.")
    if chosen.startswith("ablate-"):
        dial = chosen.removeprefix("ablate-")
        overrides = {dial: LOWEST[dial]}
    else:
        overrides = {"n_projects": int(chosen.removeprefix("n"))}
    lines.append(f"Stage C setting (largest median conflict effect among passing models): {chosen}")
    lines.append(f"  python -m eventlog run C {command_flags(manifest, overrides)}")
    return "\n".join(lines)


def stage_c_report(ok: pd.DataFrame) -> str:
    lines = []
    for model, group in ok.groupby("model"):
        table = group.pivot_table(index="version", columns="instruction", values="error_rate", aggfunc="mean")
        table = table.reindex(index=["consistent", "conflict"], columns=["none", "warning", "skill"])
        lines += [f"-- {model} (mean entity error) --", table.map(pct).to_string(), ""]
    effects = conflict_effects(ok)
    if not effects.empty:
        wide = _ordered(effects.pivot_table(index="model", columns="instruction", values="effect"))
        lines += ["Conflict effect by instruction (H3: does the skill shrink it more than the warning?)", wide.map(pct).to_string(), ""]
    conflict = ok[ok["version"] == "conflict"].pivot_table(index=["model", "seed"], columns="instruction", values="error_rate")
    consistent = ok[ok["version"] == "consistent"].pivot_table(index=["model", "seed"], columns="instruction", values="error_rate")
    recovery = pd.DataFrame({
        "skill recovery (conflict: skill - none)": (conflict["skill"] - conflict["none"]).groupby(level="model").mean(),
        "warning recovery (conflict: warning - none)": (conflict["warning"] - conflict["none"]).groupby(level="model").mean(),
        "H4 (consistent: skill - none)": (consistent["skill"] - consistent["none"]).groupby(level="model").mean(),
    })
    lines += ["Negative = fewer errors.", recovery.map(pct).to_string()]
    return "\n".join(lines)


def build_report(df: pd.DataFrame, manifest: dict) -> tuple[str, dict[str, pd.DataFrame]]:
    out: list[str] = []

    def section(title: str, body) -> None:
        text = body if isinstance(body, str) else body.to_string()
        out.extend([f"== {title} ==", text, ""])

    failures = int(df["format_failure"].sum())
    section("Coverage", (
        f"calls: {len(df)}  |  reruns for a missing ANSWER line: {int((df['attempts'] > 1).sum())}"
        f"  |  format failures (excluded): {failures}\n"
        f"tokens: {int(df['input_tokens'].sum()):,} in, {int(df['output_tokens'].sum()):,} out"
    ))
    ok = df[~df["format_failure"]]
    if ok.empty:
        return "\n".join(out), {}
    by = ["model"] + (["instruction"] if ok["instruction"].nunique() > 1 else [])

    section("Entity error rate (mean over logs)", error_table(ok))
    effects = conflict_effects(ok)
    if not effects.empty:
        section("Conflict effect (Conflict - Consistent, paired by log)", effects.assign(effect=effects["effect"].map(pct)).to_string(index=False))
    section("Adoption by trap type (single-trap projects; every trap is across the threshold, so adopted = wrong)", adoption_table(ok, by))
    if ok["version"].nunique() > 1:
        section("Spillover: error on untrapped projects", spillover_table(ok, by))
    section("Exact match, other errors, response length", other_errors_table(df))

    stage = manifest.get("stage")
    if stage == "A":
        section("Stage A decision", stage_a_decision(ok, manifest))
    elif stage == "B":
        sweep = ok[ok["setting"].str.fullmatch(r"n\d+")]
        curve = sweep[sweep["instruction"] == "none"].pivot_table(index=["model", "version"], columns="n_projects", values="error_rate", aggfunc="mean")
        curve = curve.reindex(columns=sorted(curve.columns, reverse=True))
        section("Stage B: entity error vs N", curve.map(pct))
        section("Stage B: setting for Stage C", stage_b_selection(ok, manifest))
    elif stage == "C":
        section("Stage C: six-condition table per model", stage_c_report(ok))
    return "\n".join(out), {"calls": df}
