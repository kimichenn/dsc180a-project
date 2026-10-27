# Development screen: five conflict-resolution drafts

The user stopped the 2,400-call skill-v1 study after inspecting early results and
requested three to five drafts, including general and budget-specific instructions,
tested on a small sample. This is development and selection, not a main study.

## Design frozen before collection

- GPT-6 Astra, low effort, same isolated fresh-session client as earlier runs.
- Three fresh logs: seeds 730000-730002, 1,600 records each, corrected chronological
  generator and otherwise the same generation settings as the stopped study.
- C, R, RG, E versions of each log, with equal answers and record counts.
- Six instruction conditions: no skill; three general drafts (ledger_v2, audit_v2,
  minimal_v2); two budget-specific drafts (budget_backward_v2, budget_forward_v2).
- Five repeats per combination: 3 x 4 x 6 x 5 = 360 calls. Five repeats are for
  screening only; a later validation pilot should use ten repeats per condition.
- Randomized conditions within each log, fixed schedule seed 181.
- Up to ten concurrent calls, paced at six new calls per minute.
- Each draft's exact Markdown body is frozen by its hash, along with the baseline,
  system prompts, user prompts, schedule, config, this protocol, and execution source.
- Generation and solver checks make no model calls. No extra model preflight calls.

The candidate bodies in experiment/skills/*/SKILL.md are inserted explicitly into
the system prompt. Frontmatter and skill names are not sent to the model. The
baseline gets the same task policy and answer-format instruction without an added
skill. The original skill v1 is preserved but is not a condition in this screen.
These data therefore compare each draft with no skill, not directly with v1.

## Candidate rationale

| Condition | Scope | Distinct procedure |
| --- | --- | --- |
| ledger_v2 | General | Track identifiers, dependencies, effective status, and checked combinations |
| audit_v2 | General | Build a candidate answer and challenge it against concrete evidence |
| minimal_v2 | General | Resolve only relevant conflicts, with concise tracking and verification |
| budget_backward_v2 | Budget-specific | Resolve active withdrawals backward, then sum surviving changes |
| budget_forward_v2 | Budget-specific | Replay signed changes and withdrawal effects with checkpoints |

The drafts are hypotheses about better instructions, not established improvements.
They differ in length and content; this screen does not isolate a single causal
component. Budget-task performance cannot establish transfer to other domains.

## Reporting and next-step criteria

Score the final numeric answer against the independently verified answer key.
Completed missing answers count as wrong; interrupted/no-response calls remain
missing. Wrong answers are never retried. Numerical offsets do not establish why
an error occurred.

Compare conditions on logs with every planned condition/repeat completed. Average
repeats within each log, then weight logs equally. Report accuracy by version,
overall accuracy, R/RG skill gain, C/E skill gain, per-log R/RG differences, exact
numeric-answer agreement, and output token usage. No significance tests or efficacy
claims: three logs remain three independent examples, regardless of repetition.

A candidate is worth taking to a fresh validation pilot if it improves mean R/RG
accuracy, improves R/RG on at least two of three logs, and does not reduce mean C/E
accuracy. This is a descriptive screening heuristic, not proof of effectiveness.
If several qualify, consider consistency and response cost as well as the mean.
If none qualifies, inspect errors and develop again rather than forcing a winner.
Report every candidate, including failures. Selection on this sample requires new
questions for the next validation; it cannot be validated on its selection data.

Keep wording and settings fixed throughout this screen. Stop at 360 eligible
completions or for authentication, capacity, isolation-audit, or repeated collection
errors. Do not automatically launch a 2,400-call study or an additional pilot.

Exclude all earlier trial and pilot data, the stopped run's seeds 720000-720029,
and this screen's seeds from any future main evaluation. Preserve the stopped run
as development data with its original files and attempts intact.
