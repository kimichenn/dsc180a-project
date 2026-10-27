# General conflict workflow v2: fresh development pilot

## Motivation and intervention

The user requested inspection of the clean-case degradation, a general revision,
and another small comparison with no skill. Workflow v1 scored 37/50 in C versus
46/50 for baseline. Reviewing all 100 C responses found record-range tables in
49/50 workflow responses and none of the 50 baseline responses. All 13 workflow
failures recognized that no withdrawals appeared and exposed source-inconsistent
intermediate values. Their final arithmetic agreed with their exposed tables;
this did not establish that those intermediate values were correct.

The source audit and limits are saved in the old run's analysis folder as
workflow_v1_clean_failure_review.md and workflow_v1_clean_checkpoint_audit.csv.
These observations localize visible discrepancies, but do not prove that tables,
extra reasoning, or prompt length caused the errors. Baseline failures provide
little visible intermediate evidence. Numerical offsets do not identify causes.

The new canonical candidate is the full Markdown body of
experiment/skills/conflict-resolution-workflow-v2/SKILL.md. It moves direct versus
conflict routing ahead of the ledger and status workflow. It makes segmentation,
regrouping, and reverse checks optional, distinguishes source extraction from
aggregation, and makes the response concise unless details are useful. Authority,
scope, exact revision targets, nested revisions, temporal semantics, and checks
against double counting remain. The wording has no budget-specific actors,
amounts, seeds, record ranges, or answer keys. No tools, MCP, gstack, personal
skills, external references, or delegation are enabled in evaluation calls.

This package changes wording, length, and routing together. The comparison
estimates its total effect versus baseline, not a routing-only effect or a direct
v2-minus-v1 effect. No frozen old inputs, attempts, or skill bodies are changed.

## Fixed collection plan

- Five fresh logs: seeds 760000-760004, each with 1,600 records.
- Same corrected chronological generator and settings as workflow v1.
- C/R/RG/E matched versions; none and workflow_v2; ten repeats everywhere.
- Total 400 GPT calls: 200 per instruction, 80 per log.
- GPT-6 Astra/low, isolated fresh-session Codex client, unchanged baseline format.
- Schedule seed 184; conditions randomized within each log.
- Ten concurrent calls maximum, six starts per minute; no model preflight calls.
- Validate chronology, both independent solvers, and rendered records before
  collection. Freeze the exact skill hashes, sources, prompts, records, config,
  schedule, and this protocol. Do not revise wording during collection.

## Descriptive analysis and decision

Use screen-report. Average repeats within each log and weight the five logs
equally. Only complete logs across all 80 responses enter paired comparisons.
Report accuracy for each version, overall, R/RG gains, C/E gains, all per-log
R/RG differences, exact-answer pair agreement, and output token usage. Examine
clean C separately so an improvement in E cannot conceal clean degradation.

Advance only if mean R/RG gain is positive, at least three of five logs improve
on R/RG, C accuracy does not decrease, E accuracy does not decrease, and overall
accuracy does not decrease. These stricter descriptive safeguards directly address
the observed clean harm. They are not significance thresholds or evidence of
efficacy. Report ties and degradation. Do not treat repeats as independent logs
or conduct significance tests for this five-log development pilot.

Completed eligible incorrect or missing answers count as wrong and are not
retried. Missing attempts remain missing. Stop on authentication/capacity errors,
an isolation audit failure, or repeated collection errors. Notify on completion
or a stopped run; do not restart automatically or launch additional calls.

Keep every earlier pilot separate, including the legacy 40, stopped 267,
five-draft 360, and workflow-v1 400. Exclude all prior development seeds and
760000-760004 from a future main evaluation. This is development evidence on
budget tasks; general wording does not prove cross-domain transfer. No 2,400-call
study or follow-on pilot is automatically authorized by completion.
