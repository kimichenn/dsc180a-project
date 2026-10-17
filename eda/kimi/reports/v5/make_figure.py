"""The figure for the v5 findings, computed from the raw break-phase runs (profile P0):

    python reports/v5/make_figure.py [--out <png>]

One panel per model. The version the story is about (with conflicting records) is the accent
color; the comparison (same log without them) is gray and dashed, drawn on top so both stay
visible where they agree.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))  # the experiment packages live in eda/kimi

from chain.analysis import AXIS, GRID, INK, INK_2, MUTED, SURFACE, score_frame  # noqa: E402
from chain.runner import load_chain_files  # noqa: E402
from harness.runs import load_responses  # noqa: E402

RUNS = [BASE / "results/v5/break_P0", BASE / "results/v5/break_P0_long"]  # N 20-800, then 1600-3200 (flagships)
NAMES = {"gpt": "GPT-6 Astra", "claude": "Claude Opus 5.5", "gpt-small": "GPT-6 Luna", "claude-small": "Claude Haiku 5.5"}
ACCENT = "#eb6834"  # with conflicting records (reference palette slot 2)
CONTEXT = "#898781"  # without: the de-emphasis gray
OUT = Path(__file__).resolve().parent / "accuracy_vs_n.png"

# One short note per panel, in plain words, placed where that panel has no data (lower left unless listed).
NOTES = {
    "gpt": "Right every time with conflicts through 1,600.\nAt 3,200 both versions drop to 3 of 5:\nlength, not conflict.",
    "claude": "From 1,600 records on:\nwith conflicts, 3 of 10 right\nwithout, 10 of 10 right",
    "gpt-small": "Fails from 100 records on,\nwith or without conflicts.",
    "claude-small": "At 800, its answers with conflicts\nran past the length limit (scored wrong).",
}
NOTE_AT = {"gpt-small": (0.4, 0.95, "top")}  # (x, y, vertical alignment) in axes coordinates


def counts(models: list[str]) -> pd.DataFrame:
    """Correct answers and calls per model, version, and N, pooled over the runs."""
    df = pd.concat([score_frame(load_responses(run), load_chain_files(run)) for run in RUNS], ignore_index=True)
    df = df[df["model"].isin(models)]
    return df.groupby(["model", "version", "n"])["correct"].agg(correct="sum", calls="count").reset_index()


def style(ax, levels: list[int], top: int) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_xscale("log")
    ax.set_xlim(levels[0] / 1.35, levels[-1] * 1.35)
    ax.set_xticks(levels)
    ax.set_xticklabels([f"{n:,}" for n in levels])
    ax.minorticks_off()
    ax.set_ylim(-0.3, top + 0.3)
    ax.set_yticks(range(top + 1))
    ax.yaxis.grid(True, color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=MUTED, length=0, labelsize=8.5)


def draw(models: list[str], out: Path, ncols: int) -> None:
    table = counts(models)
    levels = sorted(table["n"].unique())
    top = int(table["calls"].max())
    rows = -(-len(models) // ncols)
    plt.rcParams["font.family"] = ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"]
    fig, axes = plt.subplots(rows, ncols, figsize=(4.3 * ncols, 3.3 * rows + 0.5), sharex=True, sharey=True, squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    for ax, model in zip(axes.flat, models):
        style(ax, levels, top)
        # Where the versions agree, the small gray dot sits inside the larger orange one, so both show.
        for version, color, line, size in (("conflict", ACCENT, "-", 10), ("control", CONTEXT, (0, (4, 3)), 4.5)):
            sub = table[(table["model"] == model) & (table["version"] == version)].sort_values("n")
            ax.plot(sub["n"], sub["correct"], color=color, linestyle=line, linewidth=2, solid_capstyle="round",
                    marker="o", markersize=size, markerfacecolor=color, markeredgecolor=SURFACE, markeredgewidth=1.2,
                    zorder=3 if version == "conflict" else 4)
        ran = table[table["model"] == model]["n"].max()
        if ran < levels[-1]:
            ax.text(ran * 1.6, top / 2, f"not run past {ran:,}", fontsize=8, color=MUTED, va="center")
        ax.set_title(NAMES[model], loc="left", fontsize=10.5, color=INK, pad=6)
        x, y, va = NOTE_AT.get(model, (0.02, 0.05, "bottom"))
        ax.text(x, y, NOTES[model], transform=ax.transAxes, fontsize=8.5, color=INK_2, va=va, linespacing=1.4,
                bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 2}, zorder=5)
    for ax in axes[:, 0]:
        ax.set_ylabel(f"correct (out of {top})", fontsize=9, color=INK_2)
    for ax in axes[-1]:
        ax.set_xlabel("records in the log", fontsize=9, color=INK_2)
    for ax in axes.flat[len(models):]:
        ax.set_visible(False)
    legend = [
        Line2D([], [], color=ACCENT, linewidth=2, marker="o", markersize=10, markeredgecolor=SURFACE, label="log with conflicting records"),
        Line2D([], [], color=CONTEXT, linewidth=2, linestyle=(0, (4, 3)), marker="o", markersize=4.5, markeredgecolor=SURFACE, label="same log without them (same answer)"),
    ]
    fig.legend(handles=legend, loc="lower center", bbox_to_anchor=(0.5, 0.005), ncol=2, frameon=False, fontsize=9.5, labelcolor=INK_2)
    fig.tight_layout(rect=(0, 0.45 / fig.get_figheight(), 1, 1))
    fig.savefig(out, dpi=200, facecolor=SURFACE)
    plt.close(fig)
    print(table.pivot_table(index=["model", "version"], columns="n", values="correct").to_string())
    print(f"wrote {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT, help=f"output PNG (default: {OUT.name} beside this script)")
    args = parser.parse_args()
    draw(list(NAMES), args.out, ncols=2)


if __name__ == "__main__":
    main()
