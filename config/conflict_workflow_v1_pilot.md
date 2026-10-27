# Structured general conflict-resolution workflow: development pilot

## Revision and rationale

The user requested a richer general skill inspired by the structure of gstack,
without loading gstack into the experiment. The pending minimal-v3 preparation
was stopped before creating a manifest or making any model calls. Its original
draft and configuration are preserved as an untested alternative.

The new candidate is `workflow_v1`, whose full canonical body is
`experiment/skills/conflict-resolution-workflow-v1/SKILL.md`. It uses six phases:
decision rules, evidence and dependencies, effective status, state construction,
verification and repair, and delivery. It includes an evidence record schema,
a decision table, phase checkpoints, and four short examples outside budgeting.
Every part of the body, including the examples, is injected. No external reference
file, gstack instructions, tools, MCP, personal memory, or agent delegation is used.
The baseline receives the same task, policy, and answer format without this body.

The installed gstack investigate and plan-eng-review skills were read as design
references for phased workflows, evidence requirements, decision branches, and
verification. Their commands, hooks, integrations, telemetry, and automatic
skill routing were not run or copied into this candidate. This is an original
standalone experimental instruction, not an invocation or evaluation of gstack.

The completed minimal-v2 failure review found 11 incorrect answers in 60 calls,
including four in C/E. Three visible checkpoint tables localized discrepancies,
but did not prove their underlying causes. The workflow explicitly separates
validity, coverage, and derivation checks, and distinguishes historical checkpoints
from prefixes of finally effective items. These are revision hypotheses, not
established explanations or fixes. A previous longer ledger draft also failed to
beat baseline overall; verbosity alone is not evidence of improvement.

This intervention changes structure, length, examples, and wording together.
The injected body is 1,056 whitespace-delimited words, versus 115 for minimal v2
and 179 for the untested minimal v3; input length and response token costs matter.
A result estimates the effect of the entire package against no skill. It cannot
identify which component helped or establish an improvement over minimal v2/v3.

## Fixed design

- Five new logs: seeds 750000-750004, 1,600 records each.
- Corrected chronological generator, identical settings to the completed screen.
- Four answer-matched versions: C, R, RG, E.
- Two arms: none and workflow_v1; ten repeats in every cell.
- Total: 5 x 4 x 2 x 10 = 400 GPT calls, 200 per arm.
- GPT-6 Astra, low effort, isolated Codex client, fresh session per call, no tools.
- Schedule seed 183; randomized conditions within each log.
- Ten concurrent calls maximum, six starts per minute; no preflight model calls.
- Freeze exact instruction hashes, prompts, records, configuration, source, and
  this protocol before collection. Validate every generated log with both solvers,
  chronological checks, and rendered-text checks. Never edit a frozen candidate.

## Analysis and decision

Use `screen-report`. Average the ten repeats within each log, then weight logs
equally. Paired summaries use only logs complete in all 80 scheduled responses.
Report each version's accuracy, R/RG and C/E paired gains, overall accuracy,
per-log R/RG differences, exact-answer agreement, and output token usage. Report
wrong and missing answers; do not retry completed eligible responses. Missing
attempts stay missing rather than being imputed as failures.

The candidate merits further validation only if mean R/RG gain is positive,
at least three of five logs have positive R/RG gains, and mean C/E accuracy does
not decrease. This is a descriptive development heuristic, not a significance
threshold. Inspect individual conditions and repeatability even if it passes.
Report ties and degradation. Do not run significance tests on this five-log
development pilot or treat repeated calls as independent questions.

Keep all earlier results separate. In particular, neither the legacy 40-call
pilot, the stopped 267-response study, nor the completed 360-call draft screen
is a control group for this run. There are no minimal-v3 responses to compare.
The hand-worked boundary examples are design checks, not model evaluation data.
General wording and examples do not demonstrate cross-domain transfer; this
pilot still measures only synthetic budget-record tasks.

Stop at 400 eligible responses, or on authentication/capacity errors, an isolation
audit failure, or repeated collection errors. Notify the user on completion or
a stopped run. Do not automatically launch further calls or the 2,400-call study.
All prior development seeds, the superseded 740000-740004 seeds, and these new
750000-750004 seeds remain excluded from a future main evaluation.
