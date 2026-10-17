"""Tables, the main figure, and the phase decision rules for v5. Each response is exactly right or wrong.

Accuracy counts every call: format failures and truncations are wrong, and are also reported on
their own. A response longer than the model's max_output_tokens counts as truncated even when
the CLI let it finish (Claude Code resumes up to three times past the limit); the API would have
cut it off before its ANSWER line.
"""

from __future__ import annotations

import math
from dataclasses import fields

import pandas as pd

from chain.dials import ESCALATION, PROFILES
from chain.resolver import LURES
from chain.runner import VERSIONS
from chain.scoring import CATEGORIES, score_response
from harness.runs import CHARS_PER_TOKEN

FLAGSHIPS = ("gpt", "claude", "gemini")
MODEL_ORDER = ("gpt", "claude", "gemini", "gpt-small", "claude-small", "gemini-small")
BREAK_AT = 0.5  # break point: the smallest N where conflict accuracy is at most 50%
CONTROL_FLOOR = 0.8  # the sweep keeps a model only if control accuracy at the smallest N is at least 80%
SWEEP_LEVEL_COUNT = 6
FAILURES_PER_MODEL = 10
FULL_LOG_MAX_N = 100  # failures.md prints whole logs only up to this N

# Reference palette (validated): categorical slots in fixed order, one per model, plus chrome and ink.
COLORS = dict(zip(MODEL_ORDER, ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300")))
SURFACE, INK, INK_2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"


def score_frame(rows: list[dict], chain_files: dict[str, dict]) -> pd.DataFrame:
    records = []
    for row in rows:
        meta = chain_files[row["chain_id"]]
        scored = score_response(row["response"], row.get("finish_reason"), meta, row["version"])
        over_limit = (row.get("output_tokens") or 0) > row["max_output_tokens"]
        category = "truncated" if over_limit else scored["category"]
        records.append({
            "job_id": row["job_id"],
            "chain_id": row["chain_id"],
            "model": row["model"],
            "provider": row["provider"],
            "model_id": row["model_id"],
            "n": row["n"],
            "seed": row["seed"],
            "version": row["version"],
            "instruction": row["instruction"],
            "expected": meta["answer"],
            "value": scored["value"],
            "category": category,
            "answered_as": scored["category"],  # what the answer would score if the length limit were ignored
            "correct": category == "correct",
            "format_failure": scored["format_failure"],
            "truncated": scored["truncated"] or over_limit,
            "over_limit": over_limit,
            # Claude Code runs with no tools at all; more than one turn there means it resumed after the output limit.
            "used_tool": bool(row.get("tool_calls")) and row["provider"] != "claude-code",
            "attempts": row.get("attempts", 1),
            "input_tokens": row.get("input_tokens", 0),
            "output_tokens": row.get("output_tokens", 0),
            "latency_s": row.get("latency_s"),
            "harness": row.get("harness"),
        })
    return pd.DataFrame(records)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, center - half), min(1.0, center + half)


def ordered_models(models) -> list[str]:
    present = set(models)
    return [m for m in MODEL_ORDER if m in present] + sorted(present - set(MODEL_ORDER))


def accuracy_table(df: pd.DataFrame) -> pd.DataFrame:
    """One row per model x N x version: correct, calls, accuracy, and the Wilson 95% interval."""
    grouped = df.groupby(["model", "n", "version"])["correct"].agg(["sum", "count"]).reset_index()
    grouped.columns = ["model", "n", "version", "correct", "calls"]
    grouped["accuracy"] = grouped["correct"] / grouped["calls"]
    bounds = [wilson(int(k), int(n)) for k, n in zip(grouped["correct"], grouped["calls"])]
    grouped["lo"], grouped["hi"] = zip(*bounds)
    return grouped


def break_points(acc: pd.DataFrame) -> dict[str, dict[str, int | None]]:
    """Per model and version: the smallest N whose accuracy is at most BREAK_AT, or None."""
    points: dict[str, dict[str, int | None]] = {}
    for model in ordered_models(acc["model"].unique()):
        points[model] = {}
        for version in VERSIONS:
            sub = acc[(acc["model"] == model) & (acc["version"] == version)].sort_values("n")
            broken = sub[sub["accuracy"] <= BREAK_AT]
            points[model][version] = int(broken["n"].iloc[0]) if len(broken) else None
    return points


def _cell(row) -> str:
    return f"{int(row.correct)}/{int(row.calls)} {row.accuracy:4.0%} [{row.lo:.0%}-{row.hi:.0%}]"


def accuracy_text(acc: pd.DataFrame) -> str:
    wide = acc.assign(cell=[_cell(r) for r in acc.itertuples()]).pivot_table(index=["model", "version"], columns="n", values="cell", aggfunc="first")
    order = [(m, v) for m in ordered_models(acc["model"].unique()) for v in VERSIONS if (m, v) in wide.index]
    return wide.reindex(order).to_string()


def gap_text(acc: pd.DataFrame) -> str:
    wide = acc.pivot_table(index="model", columns=["version", "n"], values="accuracy")
    if "conflict" not in wide.columns.get_level_values(0) or "control" not in wide.columns.get_level_values(0):
        return "(needs both versions)"
    gap = (wide["conflict"] - wide["control"]).reindex(ordered_models(wide.index))
    return gap.map(lambda x: "" if pd.isna(x) else f"{100 * x:+.0f}").to_string()


def category_table(df: pd.DataFrame) -> pd.DataFrame:
    """Calls per model x version in each category (correct first, format failures and truncations last)."""
    table = df.groupby(["model", "version", "category"]).size().unstack("category", fill_value=0)
    table = table.reindex(columns=[c for c in CATEGORIES if c in table.columns or c in ("format_failure", "truncated")], fill_value=0)
    order = [(m, v) for m in ordered_models(df["model"].unique()) for v in VERSIONS if (m, v) in table.index]
    return table.reindex(order)


def _changed(a: str, b: str) -> str:
    pa, pb = PROFILES[a], PROFILES[b]
    return ", ".join(f"{f.name}={getattr(pb, f.name)}" for f in fields(pa) if getattr(pa, f.name) != getattr(pb, f.name))


def _fits(manifest: dict, chain_files: dict[str, dict], models: list[str], n_new: int) -> bool:
    """Whether every model's context window holds a prompt at n_new, scaled from the longest saved log."""
    longest = max(chain_files.values(), key=lambda c: c["n"])
    chars = max(len(longest["conflict"]), len(longest["control"])) * n_new / longest["n"] + len(manifest.get("system_prompt", ""))
    for model in models:
        config = manifest["models"][model]
        window = config.get("context_window")
        if window and chars / CHARS_PER_TOKEN[config["provider"]] > window:
            return False
    return True


def _nice(x: float) -> int:
    """Round to two significant figures (e.g. 1393 -> 1400)."""
    digits = max(0, int(math.floor(math.log10(x))) - 1)
    return int(round(x / 10**digits) * 10**digits)


def sweep_levels(points: list[int], levels: list[int], count: int = SWEEP_LEVEL_COUNT) -> list[int]:
    """Log-spaced levels from one break level below the earliest break point to one above the latest."""
    below = [n for n in levels if n < min(points)]
    above = [n for n in levels if n > max(points)]
    lo = below[-1] if below else min(points) // 2
    hi = above[0] if above else max(points) * 2
    return sorted({_nice(lo * (hi / lo) ** (i / (count - 1))) for i in range(count)})


def decision(acc: pd.DataFrame, points: dict, manifest: dict, chain_files: dict[str, dict]) -> str:
    models = list(points)
    levels = sorted(manifest.get("levels") or acc["n"].unique())
    smallest, largest = levels[0], levels[-1]
    profile = manifest.get("profile_name", "P0")
    lines = []

    falls = [m for m in models if points[m]["control"] is not None and (points[m]["conflict"] is None or points[m]["control"] <= points[m]["conflict"])]
    for model in falls:
        lines.append(
            f"FLAG {model}: control breaks at N={points[model]['control']}, no later than conflict "
            f"({points[model]['conflict'] or 'never'}). Length and tracking, not conflict, explain this model's drop."
        )
    if falls:
        lines.append("")

    control_small = acc[(acc["n"] == smallest) & (acc["version"] == "control")].set_index("model")["accuracy"]
    keep = [m for m in models if control_small.get(m, 0) >= CONTROL_FLOOR]
    dropped = [m for m in models if m not in keep]
    floor_note = [f"drop {m}: control accuracy {control_small.get(m, float('nan')):.0%} at N={smallest} is below the {CONTROL_FLOOR:.0%} floor" for m in dropped]

    if manifest.get("phase") == "sweep":
        return "\n".join(lines + (floor_note or [f"Every model passes the control floor ({CONTROL_FLOOR:.0%} at N={smallest})."]))

    flagships = [m for m in FLAGSHIPS if m in models]
    survivors = [m for m in flagships if points[m]["conflict"] is None]
    if survivors:
        step = ESCALATION.index(profile) if profile in ESCALATION else len(ESCALATION) - 1
        lines.append(f"{', '.join(survivors)} stay above {BREAK_AT:.0%} conflict accuracy at N={largest} under {profile}.")
        if step + 1 >= len(ESCALATION):
            lines.append("No escalation profile is left: report that these flagships survive the hardest profile.")
            return "\n".join(lines)
        nxt = ESCALATION[step + 1]
        new_levels = levels + [2 * largest] if _fits(manifest, chain_files, flagships, 2 * largest) else levels
        extra = f" N={2 * largest} fits every flagship's context window, so it is added." if len(new_levels) > len(levels) else ""
        lines.append(f"Escalate to {nxt} ({_changed(profile, nxt)}).{extra} The small models already have break points, so only the flagships run:")
        lines.append(f"  python -m chain run break --profile {nxt} --models {' '.join(flagships)} --levels {' '.join(map(str, new_levels))} --out results/v5/break_{nxt}")
        return "\n".join(lines)

    broken = [points[m]["conflict"] for m in models if points[m]["conflict"] is not None]
    sweep = sweep_levels(broken, levels)
    lines.append(f"Every flagship breaks under {profile}: freeze it. Break points: " + ", ".join(f"{m} N={points[m]['conflict']}" for m in models if points[m]["conflict"]))
    lines += floor_note
    lines.append("Sweep with fresh seeds (dry run first to see the plan):")
    lines.append(f"  python -m chain run sweep --profile {profile} --models {' '.join(keep)} --levels {' '.join(map(str, sweep))} --dry-run")
    return "\n".join(lines)


def plot(acc: pd.DataFrame, points: dict, manifest: dict, path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    models = ordered_models(acc["model"].unique())
    levels = sorted(acc["n"].unique())
    plt.rcParams["font.family"] = ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"]
    fig, axes = plt.subplots(1, len(models), figsize=(2.8 * len(models) + 0.6, 3.6), sharex=True, sharey=True, squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    for ax, model in zip(axes[0], models):
        color = COLORS.get(model, INK_2)
        ax.set_facecolor(SURFACE)
        ax.axhline(BREAK_AT, color=MUTED, linewidth=1, linestyle=":", zorder=1)
        for version, style, offset in (("conflict", "-", 0.96), ("control", "--", 1.04)):
            sub = acc[(acc["model"] == model) & (acc["version"] == version)].sort_values("n")
            if sub.empty:
                continue
            x = sub["n"].to_numpy() * offset  # dodge so the two intervals do not overlap
            y = sub["accuracy"].to_numpy()
            ax.errorbar(x, y, yerr=[y - sub["lo"].to_numpy(), sub["hi"].to_numpy() - y], fmt="none", ecolor=color, elinewidth=1, alpha=0.35, zorder=2)
            filled = version == "conflict"
            ax.plot(x, y, linestyle=style, linewidth=2, color=color, marker="o", markersize=6,
                    markerfacecolor=color if filled else SURFACE, markeredgecolor=color, markeredgewidth=1.5, zorder=3)
        point = points[model]["conflict"]
        note = f"conflict breaks at N={point}" if point else f"no break up to N={levels[-1]}"
        model_id = manifest.get("models", {}).get(model, {}).get("model", "")
        ax.set_title(f"{model}  {model_id}", fontsize=9.5, color=INK, loc="left", pad=16)
        ax.text(0, 1.03, note, transform=ax.transAxes, fontsize=8, color=INK_2)  # above the plot, clear of the data
        ax.set_xscale("log")
        ax.set_xticks(levels)
        ax.set_xticklabels([str(n) for n in levels], fontsize=8)
        ax.minorticks_off()
        ax.set_ylim(-0.04, 1.06)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1])
        ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
        ax.yaxis.grid(True, color=GRID, linewidth=1)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=MUTED, length=0, labelsize=8)
        ax.set_xlabel("records in the log (N, log scale)", fontsize=8.5, color=INK_2)
    axes[0][0].set_ylabel("accuracy", fontsize=9, color=INK_2)
    legend = [
        Line2D([], [], color=INK_2, linewidth=2, marker="o", markersize=6, label="conflict"),
        Line2D([], [], color=INK_2, linewidth=2, linestyle="--", marker="o", markersize=6, markerfacecolor=SURFACE, label="control"),
        Line2D([], [], color=MUTED, linewidth=1, linestyle=":", label=f"break threshold ({BREAK_AT:.0%})"),
    ]
    fig.legend(handles=legend, loc="upper right", ncol=3, frameon=False, fontsize=8.5, labelcolor=INK_2)
    phase, profile = manifest.get("phase", ""), manifest.get("profile_name", "")
    fig.suptitle(f"Budget-chain accuracy vs. log length ({phase} phase, {profile}); bars are Wilson 95% intervals", x=0.01, ha="left", fontsize=10.5, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(path, dpi=200, facecolor=SURFACE)
    plt.close(fig)


def failures_markdown(df: pd.DataFrame, chain_files: dict[str, dict], rows_by_job: dict[str, dict]) -> str:
    out = ["# Wrong responses for reading", "",
           f"Up to {FAILURES_PER_MODEL} per model, shortest logs first. Logs longer than N={FULL_LOG_MAX_N} show their first and last 15 records; the full chain is in `chains/`.", ""]
    for model in ordered_models(df["model"].unique()):
        wrong = df[(df["model"] == model) & ~df["correct"]].sort_values(["n", "version", "seed"]).head(FAILURES_PER_MODEL)
        out += [f"## {model} ({len(df[(df['model'] == model) & ~df['correct']])} wrong in all)", ""]
        if wrong.empty:
            out += ["None.", ""]
        for r in wrong.itertuples():
            chain = chain_files[r.chain_id]
            lures = chain["lures"][r.version]
            matched = f"`{r.category}`" + (f" (answered as `{r.answered_as}`)" if r.answered_as != r.category else "")
            out += [
                f"### {r.job_id}",
                f"- expected **{r.expected}**, answered **{r.value if r.value is not None else 'no ANSWER line'}**, category {matched}",
                "- lures: " + ", ".join(f"{name} {lures[name]}" for name in LURES),
                f"- {r.output_tokens:,} output tokens, {r.attempts} attempt(s)",
                "",
            ]
            lines = chain[r.version].splitlines()
            records = [line for line in lines if line.startswith("#")]
            if r.n > FULL_LOG_MAX_N:
                shown = "\n".join(records[:15] + [f"... ({len(records) - 30} records omitted; full log in chains/{r.chain_id}.json) ..."] + records[-15:])
            else:
                shown = chain[r.version]
            response = rows_by_job[r.job_id]["response"] or ""
            if len(response) > 3000:
                response = f"[... first {len(response) - 3000:,} characters omitted ...]\n" + response[-3000:]
            out += ["<details><summary>log</summary>", "", "```", shown, "```", "</details>", "",
                    "<details><summary>response</summary>", "", "```", response, "```", "</details>", ""]
    return "\n".join(out)


def build_report(df: pd.DataFrame, manifest: dict, chain_files: dict[str, dict]) -> tuple[str, dict]:
    out: list[str] = []

    def section(title: str, body: str) -> None:
        out.extend([f"== {title} ==", body, ""])

    acc = accuracy_table(df)
    points = break_points(acc)
    harnesses = ", ".join(sorted({h for h in df["harness"].dropna()})) or "API"
    section("Coverage", "\n".join([
        f"{manifest.get('phase', '?')} phase, profile {manifest.get('profile_name', '?')}: {len(df)} calls, "
        f"{df['model'].nunique()} models, N {', '.join(map(str, sorted(df['n'].unique())))}",
        f"reruns for a missing ANSWER line: {int((df['attempts'] > 1).sum())}  |  format failures: {int(df['format_failure'].sum())}  |  "
        f"truncated: {int(df['truncated'].sum())} (past the output limit: {int(df['over_limit'].sum())})  |  used a tool: {int(df['used_tool'].sum())}",
        f"tokens: {int(df['input_tokens'].sum()):,} in, {int(df['output_tokens'].sum()):,} out  |  harness: {harnesses}",
    ]))
    section("Accuracy (correct/calls, accuracy, Wilson 95% interval); format failures and truncations count as wrong", accuracy_text(acc))
    section("Conflict - control accuracy (points)", gap_text(acc))
    section(f"Break points (smallest N with accuracy <= {BREAK_AT:.0%})", "\n".join(
        f"  {m:13} conflict {points[m]['conflict'] or 'none':>5}   control {points[m]['control'] or 'none':>5}" for m in points))
    section("Error categories (calls per category; the first matching lure wins)", category_table(df).to_string())
    over = df[df["over_limit"]]
    if len(over):
        section("Responses past the output limit (scored as truncated)", "\n".join(
            f"  {r.job_id}: {r.output_tokens:,} output tokens, answer would score as {r.answered_as}" for r in over.itertuples()))
    section("Decision", decision(acc, points, manifest, chain_files))
    errors = df[~df["correct"]][["job_id", "model", "model_id", "n", "seed", "version", "expected", "value", "category", "answered_as",
                                "format_failure", "truncated", "over_limit", "output_tokens"]]
    return "\n".join(out), {"acc": acc, "points": points, "errors": errors}
