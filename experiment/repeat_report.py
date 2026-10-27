"""Paired accuracy and within-prompt variability for frozen repeat studies.

Incomplete logs are reported as progress, never imputed as failed calls. Completed
responses without an answer count as wrong. Repeats are averaged within a log.
"""
from __future__ import annotations

import csv
import itertools
import json
import random
import statistics
from collections import Counter, defaultdict

from experiment.runs import counted, read_attempts
from experiment.scoring import hit_length_limit, score


def interval(values, draws=10000):
    rng = random.Random(180)
    samples = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(draws))
    return samples[int(.025 * (draws - 1))], samples[int(.975 * (draws - 1))]


def sign_flip_p(values):
    values = [v for v in values if v != 0]
    if not values:
        return 1.0
    observed = abs(sum(values))
    if len(values) <= 20:
        sums = [0.0]
        for value in values:
            sums = [s + value for s in sums] + [s - value for s in sums]
        return sum(abs(s) >= observed - 1e-10 for s in sums) / len(sums)
    rng = random.Random(181)
    extreme = sum(abs(sum(v if rng.random() < .5 else -v for v in values)) >= observed - 1e-10
                  for _ in range(100000))
    return (extreme + 1) / 100001


def holm(values):
    result = [0.0] * len(values)
    running = 0.0
    for rank, i in enumerate(sorted(range(len(values)), key=values.__getitem__)):
        running = max(running, min(1, (len(values) - rank) * values[i]))
        result[i] = running
    return result


def agreement(values):
    # All pairs are in the denominator. Two missing answers never count as a match.
    pairs = list(itertools.combinations(values, 2))
    return (sum(a is not None and b is not None and a == b for a, b in pairs) / len(pairs)) if pairs else None


def complete_main_cells(trials, results, repeats):
    base = [t for t in trials if t.repeat <= repeats]
    worlds = defaultdict(list)
    for t in base:
        worlds[t.model, t.world_id].append(t)
    complete = {key for key, group in worlds.items() if all(t.trial_id in results for t in group)}
    cells = defaultdict(list)
    for t in base:
        if (t.model, t.world_id) in complete:
            cells[t.model, t.world_id, t.instruction, t.version].append(results[t.trial_id])
    return cells, complete


def repeat_report(run):
    if set(run.config.instructions) != {"none", "skill"}:
        raise ValueError("use screen-report for a comparison of multiple skill drafts")
    chosen = counted(read_attempts(run))
    results, scored_rows = {}, []
    for t in run.trials:
        if t.trial_id not in chosen:
            continue
        a = chosen[t.trial_id]
        r = score(a['response'], run.keys[t.world_id], hit_length_limit(
            a['usage'], a.get('stop_reason'), run.config.models[t.model].max_output_tokens))
        results[t.trial_id] = r
        scored_rows.append(dict(trial=t.trial_id, model=t.model, world=t.world_id, version=t.version,
            instruction=t.instruction, repeat=t.repeat, correct=r['correct'], answer=r['value'],
            expected=r['expected'], error=r['error'],
            status='correct' if r['correct'] else r['bucket'] if r['bucket'] in ('gave_up', 'cut_off') else 'wrong_number',
            input_tokens=a['usage'].get('input_tokens'), output_tokens=a['usage'].get('output_tokens')))
    cells, complete = complete_main_cells(run.trials, results, run.config.repeats)
    means = {key: statistics.mean(r['correct'] for r in rows) for key, rows in cells.items()}
    accuracy, effects, variability = [], [], []
    lines = [f'{run.path.name}: {len(results)}/{len(run.trials)} eligible responses collected',
             f'{run.config.logs} fresh logs; {run.config.repeats} base repeats per condition.',
             'Accuracy/effects use only logs complete across all base conditions; interim results are descriptive.']
    for model in run.config.models:
        worlds = sorted(w for m, w in complete if m == model)
        lines += ['', f'{model}: {len(worlds)}/{run.config.logs} complete base logs',
                  'Version  No skill    Skill       Paired skill gain']
        for version in run.config.versions:
            arm_values = {arm: [means[model, w, arm, version] for w in worlds] for arm in ('none', 'skill')}
            if not worlds:
                lines.append(f'{version:<8} pending')
                continue
            for arm, values in arm_values.items():
                lo, hi = interval(values)
                row = dict(model=model, version=version, instruction=arm, logs=len(worlds),
                           accuracy=statistics.mean(values), ci_low=lo, ci_high=hi)
                # Exact one-sided upper bound for probability a log has any error.
                if all(v == 1 for v in values):
                    row['any_error_log_upper_95'] = 1 - .05 ** (1 / len(values))
                accuracy.append(row)
            gain = statistics.mean(arm_values['skill']) - statistics.mean(arm_values['none'])
            lines.append(f"{version:<8} {statistics.mean(arm_values['none']):<11.1%} {statistics.mean(arm_values['skill']):<11.1%} {100*gain:+.1f} pp")
        if not worlds:
            continue
        comparisons = {
            'H1: E minus R without skill': [means[model,w,'none','E']-means[model,w,'none','R'] for w in worlds],
            'H2: skill gain averaged over R and RG': [sum(means[model,w,'skill',v]-means[model,w,'none',v] for v in ('R','RG'))/2 for w in worlds],
        }
        for name, values in comparisons.items():
            lo, hi = interval(values)
            effects.append(dict(model=model, comparison=name, logs=len(worlds), nonzero_logs=sum(v != 0 for v in values),
                                estimate_pp=100*statistics.mean(values), ci_low_pp=100*lo, ci_high_pp=100*hi,
                                p=sign_flip_p(values)))
    # Two tests per configured model. Unavailable tests remain in the correction family.
    adjusted = holm([row['p'] for row in effects] + [1.0] * (2*len(run.config.models)-len(effects)))
    for row, p in zip(effects, adjusted):
        row['p_holm'] = p
        lines.append(f"{row['model']} {row['comparison']}: {row['estimate_pp']:+.1f} pp "
                     f"(95% CI {row['ci_low_pp']:+.1f} to {row['ci_high_pp']:+.1f}; Holm p={p:.4g}).")
    groups = defaultdict(list)
    for t in run.trials:
        groups[t.model,t.world_id,t.instruction,t.version].append(t)
    for key, trials in groups.items():
        if not all(t.trial_id in results for t in trials):
            continue
        rows = [results[t.trial_id] for t in sorted(trials, key=lambda t:t.repeat)]
        values = [r['value'] for r in rows]
        right = sum(r['correct'] for r in rows)
        variability.append(dict(model=key[0], world=key[1], instruction=key[2], version=key[3],
            repeats=len(rows), correct=right, accuracy=right/len(rows), exact_answer_agreement=agreement(values),
            distinct_numeric_answers=len({v for v in values if v is not None}), missing_answers=sum(v is None for v in values),
            same_wrong_every_time=right==0 and all(v is not None for v in values) and len(set(values))==1))
    hist = Counter((r['model'],r['instruction'],r['version'],r['repeats'],r['correct']) for r in variability)
    histogram = [dict(model=k[0],instruction=k[1],version=k[2],repeats=k[3],correct=k[4],logs=n)
                 for k,n in sorted(hist.items())]
    lines += ['', 'Repeatability: correct-count histograms and exact numeric-answer agreement are in the CSV tables.',
              'Missing numeric answers count as wrong and never count as matching numbers.',
              'Sign-flip inference assumes symmetric log differences under the null. Confidence intervals resample whole logs.',
              'Do not interpret repeated identical errors as proof of a particular mechanism.',
              'The instruction is general in wording; these data test only the budget task.']
    out = run.path/'analysis'; out.mkdir(exist_ok=True)
    for name, rows in [('repeat_accuracy', accuracy),('repeat_effects',effects),('repeat_variability',variability),
                       ('repeat_histogram',histogram),('repeat_scored',scored_rows)]:
        fields=list(dict.fromkeys(k for row in rows for k in row))
        with (out/f'{name}.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    report='\n'.join(lines)+'\n'
    (out/'repeat_report.txt').write_text(report)
    return report
