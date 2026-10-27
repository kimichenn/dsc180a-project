"""Descriptive skill-pilot results. No significance claims or causal error labels."""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict

from experiment.runs import Run, Trial, counted, read_attempts
from experiment.scoring import hit_length_limit, score


def paired_gains(trials: list[Trial], correct: dict[str, bool]) -> dict[tuple[str, str], list[float]]:
    """One skill-minus-baseline difference per complete log, with equal log weights.

    A cell is complete only when all its planned repeats have an eligible response.
    Missing answers in completed responses count as wrong; missing calls stay missing.
    The R/RG average requires all four cells on the same log.
    """
    cells = defaultdict(list)
    for trial in trials:
        cells[trial.model, trial.world_id, trial.version, trial.instruction].append(trial.trial_id)
    means = {
        key: statistics.mean(correct[tid] for tid in ids)
        for key, ids in cells.items() if all(tid in correct for tid in ids)
    }
    gains = defaultdict(list)
    for model, world in sorted({(t.model, t.world_id) for t in trials}):
        per_version = {}
        for version in ("C", "R", "RG", "E"):
            baseline, skill = (model, world, version, "none"), (model, world, version, "skill")
            if baseline in means and skill in means:
                per_version[version] = means[skill] - means[baseline]
                gains[model, version].append(per_version[version])
        if "R" in per_version and "RG" in per_version:
            gains[model, "R/RG average"].append((per_version["R"] + per_version["RG"]) / 2)
    return dict(gains)


def pilot_report(run: Run) -> str:
    """Save a readable report that can safely be refreshed during collection."""
    if run.config.repeatability.logs or run.config.frozen_skill_sha256:
        raise ValueError("use repeat-report for a frozen repeat study")
    chosen = counted(read_attempts(run))
    results = {}
    for trial in run.trials:
        attempt = chosen.get(trial.trial_id)
        if attempt is not None:
            limit = run.config.models[trial.model].max_output_tokens
            results[trial.trial_id] = score(
                attempt["response"], run.keys[trial.world_id],
                hit_length_limit(attempt["usage"], attempt.get("stop_reason"), limit),
            )
    gains = paired_gains(run.trials, {tid: result["correct"] for tid, result in results.items()})
    lines = [f"{run.path.name}: exploratory skill pilot", run.config.description,
             f"Collected {len(results)}/{len(run.trials)} planned eligible responses.",
             "Development data only; do not pool with the main study.",
             "No significance tests: these results guide piloting, not efficacy claims."]
    for model in run.config.models:
        trials = [t for t in run.trials if t.model == model]
        lines += ["", model, "Version  No skill (right/done/planned)  Skill (right/done/planned)  Paired gain (pp; logs)"]
        for version in run.config.versions:
            cells = []
            for arm in ("none", "skill"):
                planned = [t for t in trials if t.version == version and t.instruction == arm]
                done = [results[t.trial_id] for t in planned if t.trial_id in results]
                cells.append(f"{sum(r['correct'] for r in done)}/{len(done)}/{len(planned)}")
            differences = gains.get((model, version), [])
            effect = f"{100 * statistics.mean(differences):+.1f}; n={len(differences)}" if differences else "pending"
            lines.append(f"{version:<8} {cells[0]:<30} {cells[1]:<27} {effect}")
        pooled = gains.get((model, "R/RG average"), [])
        lines.append("R/RG average paired skill gain: " + (
            f"{100 * statistics.mean(pooled):+.1f} percentage points across {len(pooled)} complete logs."
            if pooled else "pending complete R and RG pairs."))
        done = [results[t.trial_id] for t in trials if t.trial_id in results]
        statuses = Counter("correct" if r["correct"] else r["bucket"] if r["bucket"] in ("gave_up", "cut_off")
                           else "wrong_number" for r in done)
        lines.append("Response status: " + (", ".join(f"{name}={n}" for name, n in sorted(statuses.items())) or "no responses"))
        for arm in ("none", "skill"):
            tokens = [chosen[t.trial_id]["usage"].get("output_tokens") for t in trials
                      if t.instruction == arm and t.trial_id in results]
            tokens = [n for n in tokens if n is not None]
            if tokens:
                lines.append(f"{arm} output tokens: mean {statistics.mean(tokens):.0f}, max {max(tokens)}.")
    lines += ["", "Paired gains use only logs with every planned repeat in the compared cells.",
              "Cell counts include all observed responses, including incomplete pairs.",
              "One repeat cannot measure repeatability. See PILOT_NOTES.md for run limitations."]
    report = "\n".join(lines) + "\n"
    out = run.path / "analysis"
    out.mkdir(exist_ok=True)
    (out / "pilot_report.txt").write_text(report)
    return report
