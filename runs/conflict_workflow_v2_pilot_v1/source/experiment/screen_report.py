"""Descriptive, matched comparisons for a development screen with several skills."""
from __future__ import annotations

import csv
import json
import statistics

from experiment.repeat_report import agreement, complete_main_cells
from experiment.runs import counted, read_attempts
from experiment.scoring import hit_length_limit, score


def screen_snapshot(run):
    if "none" not in run.config.instructions or not {"C", "R", "RG", "E"} <= set(run.config.versions):
        raise ValueError("screen-report requires a none baseline and C/R/RG/E versions")
    chosen = counted(read_attempts(run))
    results, scored = {}, []
    for trial in run.trials:
        if trial.trial_id not in chosen:
            continue
        attempt = chosen[trial.trial_id]
        result = score(attempt['response'], run.keys[trial.world_id], hit_length_limit(
            attempt['usage'], attempt.get('stop_reason'), run.config.models[trial.model].max_output_tokens))
        results[trial.trial_id] = result
        scored.append(dict(trial_id=trial.trial_id, model=trial.model, world=trial.world_id,
            version=trial.version, instruction=trial.instruction, repeat=trial.repeat,
            correct=result['correct'], answer=result['value'], expected=result['expected'],
            error=result['error'], status='correct' if result['correct'] else
            result['bucket'] if result['bucket'] in ('gave_up', 'cut_off') else 'wrong_number'))
    cells, complete = complete_main_cells(run.trials, results, run.config.repeats)
    means = {key: statistics.mean(r['correct'] for r in rs) for key, rs in cells.items()}
    metrics = []
    for model in run.config.models:
        worlds = sorted(w for m, w in complete if m == model)
        if not worlds:
            continue
        for arm in run.config.instructions:
            accuracy = {v: statistics.mean(means[model, w, arm, v] for w in worlds)
                        for v in run.config.versions}
            gains = [100 * statistics.mean(means[model, w, arm, v] - means[model, w, 'none', v]
                                          for v in ('R', 'RG')) for w in worlds]
            guardrail = statistics.mean(means[model, w, arm, v] - means[model, w, 'none', v]
                                        for w in worlds for v in ('C', 'E'))
            trials = [t for t in run.trials if t.model == model and t.world_id in worlds and t.instruction == arm]
            tokens = [chosen[t.trial_id]['usage'].get('output_tokens') for t in trials]
            tokens = [t for t in tokens if t is not None]
            metrics.append(dict(model=model, instruction=arm, logs=len(worlds), worlds=worlds,
                accuracy_by_version=accuracy, overall_accuracy=statistics.mean(accuracy.values()),
                conflict_accuracy=statistics.mean(accuracy[v] for v in ('R', 'RG')),
                conflict_gain_pp=statistics.mean(gains), per_log_conflict_gain_pp=gains,
                clean_explicit_gain_pp=100 * guardrail,
                mean_answer_agreement=statistics.mean(agreement([r['value'] for r in cells[model, w, arm, v]])
                    for w in worlds for v in run.config.versions) if run.config.repeats > 1 else None,
                mean_output_tokens=statistics.mean(tokens) if tokens else None))
    return dict(collected=len(results), planned=len(run.trials),
                complete_logs={m: sum(mm == m for mm, _ in complete) for m in run.config.models},
                metrics=metrics), scored


def screen_report(run):
    snapshot, scored = screen_snapshot(run)
    lines = [f'{run.path.name}: development skill screen', run.config.description,
             f"Collected {snapshot['collected']}/{snapshot['planned']} eligible responses.",
             'Matched comparisons use only logs complete across every version, instruction, and repeat.',
             'Development data only. No significance tests or claims of generalization to other tasks.']
    for model in run.config.models:
        lines += ['', f"{model}: {snapshot['complete_logs'][model]}/{run.config.logs} complete logs; "
                  f'{run.config.repeats} repeats per condition.',
                  'Instruction    C       R       RG      E       Overall R/RG gain   C/E gain']
        for row in (r for r in snapshot['metrics'] if r['model'] == model):
            accuracy = row['accuracy_by_version']
            lines.append(f"{row['instruction']:<14} " + ' '.join(f'{accuracy[v]:<7.1%}' for v in ('C','R','RG','E'))
                         + f" {row['overall_accuracy']:<7.1%} {row['conflict_gain_pp']:+6.1f} pp  "
                         + f"{row['clean_explicit_gain_pp']:+6.1f} pp")
        for row in (r for r in snapshot['metrics'] if r['model'] == model):
            gains = ', '.join(f'{value:+.1f}' for value in row['per_log_conflict_gain_pp'])
            agreement_text = f"{row['mean_answer_agreement']:.1%}" if row['mean_answer_agreement'] is not None else 'not estimable'
            token_text = f"{row['mean_output_tokens']:.0f}" if row['mean_output_tokens'] is not None else 'unavailable'
            lines.append(f"{row['instruction']}: per-log R/RG gains [{gains}] pp; "
                         f'mean exact-answer pair agreement {agreement_text}; mean output tokens {token_text}.')
    lines += ['', 'R/RG and C/E gains compare each candidate with the same no-skill logs.',
              'Repeats measure within-question variation; the independent sample is the number of logs.',
              'A leading draft needs a fresh validation pilot before any large study.',
              'Missing calls stay missing; completed responses without a numeric answer count as wrong.',
              'Wrong numerical answers are not assigned a causal mechanism from their offset.']
    out = run.path / 'analysis'
    out.mkdir(exist_ok=True)
    report = '\n'.join(lines) + '\n'
    (out / 'screen_report.txt').write_text(report)
    (out / 'screen_summary.json').write_text(json.dumps(snapshot, indent=2) + '\n')
    fields = list(scored[0]) if scored else ['trial_id', 'correct']
    with (out / 'screen_scored.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(scored)
    return report
