# Fresh pilot: minimal checklist v3 versus no skill

**Status:** Superseded before collection. At the user's request for a richer
workflow, preparation was stopped before creating a manifest or making any model
calls. The preserved plan below was not executed. The replacement design is
[conflict_workflow_v1_pilot.md](conflict_workflow_v1_pilot.md).

The user requested failure inspection, a general revision of the minimal checklist,
and a new small comparison with no skill. This is a development pilot following
selection on an earlier screen; it is not the 2,400-call main study.

## Revision and hypothesis

The prior minimal checklist scored 49/60, equal to no skill overall. Its 11 failures
included four C/E failures without withdrawal chains. Three wrong responses exposed
incorrect checkpoints: one R response was accurate through record 1400 but missed
the final result by 5; a clean response carried a +60 error from the first reported
checkpoint onward; an E response had different errors across successive blocks.

The full review is in runs/skill_drafts_pilot_v1/analysis/minimal_v2_failure_review.md
and its checkpoint CSV. These observations do not establish the model's internal
failure mechanism. Legacy numerical error labels are not treated as causal evidence.

V3 preserves the general authority and revision rules. It makes intermediate checks
explicitly refer to source records and nonoverlapping boundaries, and adds a check
of the final segment against the preceding state. It does not require a printed
table or introduce budget-specific arithmetic rules. The draft is 179 words versus
115 for v2; extra length is part of the intervention and could help or hurt.

The hypothesis is that this narrower verification change reduces combination errors
without losing the useful conflict handling. This is unproven until tested.

## Design fixed before collection

- Five fresh logs: seeds 740000-740004; 1,600 records each.
- Same corrected chronological generator and settings as the five-draft screen.
- Four matched versions: C, R, RG, E; equal answers and record counts.
- Two conditions: no skill and minimal_v3. The baseline policy and answer format
  remain identical; only the added instruction differs.
- Ten repeats per condition: 5 x 4 x 2 x 10 = 400 GPT calls (200 per arm).
- GPT-6 Astra at low reasoning effort through the same isolated fresh-session client.
- Fixed schedule seed 182, randomized conditions within each log.
- Up to ten concurrent calls, paced at six starts per minute.
- Source, Markdown candidate body, prompts, seeds, schedule, config, and this protocol
  are frozen before collection. No wording changes during the pilot.
- No model preflight calls or old-response reuse. Model calls begin only after all
  newly generated logs pass the solver, chronology, and rendered-text checks.

## Analysis and next decision

Use screen-report for descriptive paired comparisons. Average the ten repeats within
each log, then weight the five logs equally. Use only logs complete across all 80
responses for matched summaries. Report version accuracy, R/RG gain, C/E gain,
overall accuracy, per-log R/RG differences, exact-answer agreement, and token usage.
Missing calls stay missing; completed missing or wrong answers count as wrong and
are not retried. Do not run significance tests on this five-log development pilot.

Treat v3 as promising only if mean R/RG gain is positive, at least three of the five
logs have positive R/RG gains, and mean C/E accuracy does not decrease. This is a
development heuristic, not a significance threshold or proof of efficacy. Inspect
individual versions and variability even if the combined criteria pass. Report all
results, including degradation or a tie. Do not force a winner.

The earlier v2 results motivated this revision but are not a matched v2 control in
this pilot. Comparing their raw accuracy with v3 would mix different questions.
General wording is not evidence of transfer: this pilot still tests only budgets.

Stop after 400 eligible responses, or on authentication/capacity errors, an isolation
audit failure, or repeated collection errors. Notify completion or a stopped run.
Do not automatically launch another pilot or the 2,400-call study.

All earlier development seeds (including 720000-720029 and 730000-730002) and this
pilot's seeds remain excluded from a future main evaluation. Preserve original
skills, frozen runs, and attempts unchanged; do not pool their outcomes.
