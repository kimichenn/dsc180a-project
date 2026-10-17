"""Figure for the v4 EDA report, computed from the raw event-log runs:

    python reports/v4/make_figures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))  # the experiment packages live in eda/kimi

from eventlog.runner import load_log_files  # noqa: E402
from eventlog.scoring import normalize_name, parse_answer  # noqa: E402
from harness.runs import load_responses  # noqa: E402

RUNS = [BASE / "results/v4/A_step0", BASE / "results/v4/v4_small_models/A_step0"]
MODELS = {  # config alias -> display name, in plotting order (top to bottom)
    "gpt": "GPT-6 Astra",
    "claude": "Claude Opus 5.5",
    "gemini": "Gemini 3.1 Pro",
    "gpt-small": "GPT-6 Luna",
    "claude-small": "Claude Haiku 5.5",
    "gemini-small": "Gemini 3.5 Flash-Lite",
}
FAILING = ("gemini", "gpt-small")  # models with a conflict effect worth decomposing

# Reference palette (validated): slot 1 blue, slot 2 orange; chrome and ink tokens.
CONSISTENT, CONFLICT = "#2a78d6", "#eb6834"
SURFACE, INK, INK_2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"


def tally() -> dict:
    """Per model and version: wrong decisions, plus the 'skipped' and 'fooled' counts."""
    counts = {}
    for run in RUNS:
        logs = load_log_files(run)
        for row in load_responses(run):
            meta, names = logs[row["log_id"]], set(parse_answer(row["response"]) or [])
            c = counts.setdefault((row["model"], row["version"]), dict.fromkeys(
                ("wrong", "n", "skipped", "clean_in", "fooled", "trapped_out"), 0))
            for p in meta["projects"]:
                listed = normalize_name(p["name"]) in names
                c["n"] += 1
                c["wrong"] += listed != p["included"]
                if p["included"] and not p["traps"]:  # should be listed, nothing to resolve
                    c["clean_in"] += 1
                    c["skipped"] += not listed
                if not p["included"] and p["traps"]:  # listing it means believing an early trap date
                    c["trapped_out"] += 1
                    c["fooled"] += listed
    return counts


def style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=MUTED, length=0, labelsize=9)
    ax.xaxis.grid(True, color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    ax.set_xlim(0, 75)
    ax.set_xticks(range(0, 61, 20))
    ax.xaxis.set_major_formatter(lambda x, _: f"{x:.0f}%")


def fmt(rate: float) -> str:
    return f"{rate:.1f}%" if 0 < rate < 1 else f"{rate:.0f}%"


def main() -> None:
    counts = tally()
    plt.rcParams["font.family"] = ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"]
    fig, (left, right) = plt.subplots(1, 2, figsize=(11, 4.4), gridspec_kw={"width_ratios": [1.15, 1]})
    fig.patch.set_facecolor(SURFACE)

    # Panel A: share of wrong decisions per model, Consistent vs Conflict.
    style(left)
    height = 0.34
    for i, model in enumerate(MODELS):
        y = len(MODELS) - 1 - i
        for offset, version, color in ((height / 2 + 0.02, "consistent", CONSISTENT), (-height / 2 - 0.02, "conflict", CONFLICT)):
            c = counts[(model, version)]
            rate = 100 * c["wrong"] / c["n"]
            left.barh(y + offset, rate, height=height, color=color, edgecolor=SURFACE, linewidth=0)
            left.text(rate + 1, y + offset, fmt(rate), va="center", fontsize=8, color=INK_2)
    left.set_yticks(range(len(MODELS)), list(MODELS.values())[::-1], color=INK, fontsize=9.5)
    left.axhline(2.5, color=GRID, linewidth=1)
    left.text(74, 2.62, "flagship", ha="right", va="bottom", fontsize=8, color=MUTED)
    left.text(74, 2.38, "small", ha="right", va="top", fontsize=8, color=MUTED)
    left.set_title("Wrong include/exclude decisions\n(3 logs × 100 projects per bar)", loc="left", fontsize=10.5, color=INK)

    # Panel B: what the conflict errors are, for the two models that have them.
    style(right)
    rows = []
    for model in FAILING:
        rows.append((f"{MODELS[model]}: skipped a\nproject with no trap", "skipped", "clean_in", model))
        rows.append((f"{MODELS[model]}: listed a project\nbecause of its trap", "fooled", "trapped_out", model))
    for y, (label, num, den, model) in enumerate(reversed(rows)):
        before = 100 * counts[(model, "consistent")][num] / counts[(model, "consistent")][den]
        after = 100 * counts[(model, "conflict")][num] / counts[(model, "conflict")][den]
        right.plot([before, after], [y, y], color=AXIS, linewidth=2, solid_capstyle="round", zorder=1)
        for x, color in ((before, CONSISTENT), (after, CONFLICT)):
            right.plot(x, y, "o", markersize=9, color=color, markeredgecolor=SURFACE, markeredgewidth=2, zorder=2, clip_on=False)
        right.text(after + 2.5, y, f"{before:.0f}% → {after:.0f}%", va="center", fontsize=8, color=INK_2)
    right.set_yticks(range(len(rows)), [r[0] for r in reversed(rows)], color=INK, fontsize=9)
    right.set_ylim(-0.6, len(rows) - 0.4)
    right.tick_params(axis="y", pad=12)  # clear the 0% dots
    right.set_title("Where the conflict errors come from\n(share of eligible projects)", loc="left", fontsize=10.5, color=INK)

    handles = [plt.Line2D([], [], marker="s", linestyle="", markersize=9, color=color) for color in (CONSISTENT, CONFLICT)]
    fig.legend(handles, ["Consistent log (records agree)", "Conflict log (traps present)"], loc="lower center",
               ncol=2, frameon=False, fontsize=9, labelcolor=INK_2, bbox_to_anchor=(0.5, -0.01))
    fig.tight_layout(rect=(0, 0.06, 1, 1), w_pad=3)
    out = Path(__file__).resolve().parent / "event_log_results.png"
    fig.savefig(out, dpi=200, facecolor=SURFACE)
    print(f"wrote {out}")
    for model in MODELS:
        c, k = counts[(model, "consistent")], counts[(model, "conflict")]
        print(f"  {MODELS[model]:22} consistent {c['wrong']:3}/{c['n']}   conflict {k['wrong']:3}/{k['n']}"
              f"   skipped {c['skipped']}/{c['clean_in']} -> {k['skipped']}/{k['clean_in']}"
              f"   fooled {c['fooled']}/{c['trapped_out']} -> {k['fooled']}/{k['trapped_out']}")


if __name__ == "__main__":
    main()
