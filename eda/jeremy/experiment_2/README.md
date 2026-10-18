# Experiment 2: Can revoked evidence still control an LLM's answer?

Status: generator, independent answer checkers, and resumable Codex CLI batch
collector implemented. Start with [RUNNING.md](RUNNING.md). The original
[one-example starter](CODEX_CLI.md) is also preserved. Smoke checks validate the
collection machinery; they are not evidence of a frontier-model failure.
See [VALIDATION.md](VALIDATION.md) for the completed implementation checks.

## Recommendation

Give a model a long fictional approval ledger and ask which route is currently authorized. A recent approval looks official and is repeated in team summaries, but its supporting certificate may have been withdrawn several links earlier. Some withdrawals are themselves withdrawn. The model must select the latest approval whose evidence is still valid.

Use categorical route names instead of budgets. This makes the task about following evidence and authority rules, without arithmetic. A failure is useful when the model solves the matched clean ledger but fails the version with revocations or misleading summaries. A single difficult prompt is a discovery example, not a general result.

## Why this follows from the current results

- Kimi's v5 Opus results were 3/10 correct on long conflict logs and 10/10 on matched controls. Astra was 8/10 versus 7/10 at those lengths, so a reliable Astra conflict penalty remains to be found. Both models were run at low effort. [Kimi, commit 977328d](https://github.com/kimichenn/dsc180a-project/blob/977328dc52d606cb031ed7045e6e88dea1ab69f7/eda/kimi/reports/v5/findings.md)
- Jeremy's Qwen3-1.7B skill gains depended on the task: misleading update/basic and update/calculation gained about 29 and 28 points, while misleading distractor/basic and distractor/calculation lost about 11 and 15 points. There was no overall misleading-context accuracy drop. Separate updates from distractors and include a neutral instruction control. [Jeremy, commit 95495dc](https://github.com/kimichenn/dsc180a-project/blob/95495dc6f6ea63fbacf298c3d6d6c0ed1ff8e8b1/eda_results/evaluation_v1/results_v1.md)
- Multi-hop tracing is an established long-context stress test in [RULER](https://arxiv.org/abs/2404.06654). That motivates the design; it does not establish that the current models will fail it or that this proposal is a new benchmark category.

Hypothesis: revocations that invalidate dependent evidence will cause an accuracy loss beyond ordinary long-context retrieval, and misleading summaries may amplify that loss. A procedure that explicitly recomputes evidence validity may help, but it may also hurt some conditions, as Jeremy's results suggest.

## Task and exact rules

Each record has a unique ID, author, project, type, and relevant fields. Record order is chronological; “current” means the end of the supplied ledger, regardless of today's date.

1. Only the Evidence Office can issue evidence records. An evidence record may require earlier evidence records. All listed requirements must remain valid.
2. Only the Approval Office can authorize a route. An approval may require earlier evidence records. It is usable only when all those requirements remain valid.
3. Only the Audit Office can withdraw an earlier official record, including an earlier withdrawal. A withdrawal removes its target's effect. Withdrawing a withdrawal restores its target unless another active rule invalidates it. Audit withdrawals do not require supporting evidence.
4. Each record is targeted by at most one withdrawal. Targets always occur earlier. Evidence requirements also always point backward and only to evidence records. There are no cycles.
5. A record can remain active yet be invalid because required evidence is invalid. Recompute validity at the end of the ledger; an approval does not retain validity just because its evidence was valid when issued.
6. The highest-ID valid approval for the queried project determines its route. Every project has an unconditional fallback approval that is never withdrawn, so there is always exactly one answer.
7. Team messages and summaries cannot authorize routes, validate evidence, or cancel official records, regardless of repetition or confident wording.

Use four arbitrary route labels with balanced correct answers. Rotate names, projects, IDs, and winning positions. Include both reinstatements and effective cancellations so “reject the newest approval” is not a dependable shortcut.

## Small worked example

```text
R001 Approval Office: Project Orion may use AMBER. No requirements.
R002 Evidence Office: Certificate C1 is issued. No requirements.
R003 Evidence Office: Clearance C2 is issued; requires R002.
R004 Approval Office: Project Orion may use BLUE; requires R003.
R005 Audit Office: Withdraw R002.
R006 Audit Office: Withdraw R005.
R007 Audit Office: Withdraw R006.
R008 Team summary: Orion's approved route is BLUE.

Question: Which route is authorized for Orion at the end of the ledger?
```

Correct output:

```json
{"route":"AMBER","approval_id":"R001"}
```

R007 cancels R006, leaving R005 effective. R002 is therefore withdrawn, which invalidates R003 and then R004. The fallback R001 wins. If R007 is replaced with a harmless message, R006 stands, R002 is restored, and BLUE wins. This counterfactual is a hand-check for nested withdrawal semantics.

## Four matched context conditions

| Code | Revocations and invalid dependent evidence | Misleading team summaries | Purpose |
|---|---|---|---|
| C | Removed | Absent | Long-context baseline |
| G | Removed | Present | Gossip effect |
| R | Present | Absent | Revocation and dependency effect |
| RG | Present | Present | Combined effect |

Build each group of four from one generated world, rather than generating each condition independently.

Start with the R ledger and resolve it. To produce C, replace every withdrawal and every invalid evidence/approval record with a harmless message from the same author in the same position. Keep every valid evidence/approval record and its requirements unchanged. This preserves the latest valid approval and the exact answer. It also preserves the surviving dependency graph. Removing invalid alternatives is an intentional part of the revocation treatment, so do not claim the comparison isolates withdrawal wording alone.

Reserve eight team-message slots at identical positions. Use harmless messages for C/R and the same incorrect route claim for G/RG. Balance the slots across the beginning, middle, and end; do not always place the lure last. All summaries remain ordinary user-provided source material, never system/developer instructions or prior assistant answers.

Match record count exactly. The implementation pads a labeled non-evidence appendix after the ledger and before the question, leaving all record positions unchanged. Match the rendered experimental prompt's lengths within 2% using the configured counter, and save the counts and tokenizer/version used. The default character-based counter is an estimate: exact model token matching is unverified. Confirmation preparation requires either a verified tokenizer or an explicit recorded deviation. Also record interface-reported input usage separately: Codex can add context beyond the experimental prompt. Keep author distribution, target project, output format, valid answer-bearing records, and their positions fixed across conditions. Validate the answer before rendering; padding cannot add ledger records. Randomize condition execution order and use a fresh session for every call.

## Difficulty controls

Initially use 1,600 records across 20 interleaved projects, eight candidate approvals for the target, and evidence dependency depths of 2, 4, and 8. Use shared evidence nodes with at most two requirements per node, rather than an exponentially growing tree. Spread required evidence far apart in the ledger. The generator uses three withdrawals to cancel evidence and two to reinstate it. This replaces the original all-length-three proposal so the dataset includes both outcomes. These choices stay fixed across the depth sweep.

Keep total record count, author counts, project count, and summary count constant when changing depth. More evidence nodes replace harmless filler; token matching is within each world's four contexts, not across depths. Report the depth-specific prompt estimates and actual usage rather than claiming depth is isolated from all length effects. If all depths remain easy, extend to depth 16 at the same record count. Then, if necessary, increase the ledger to 3,200 records while holding graph difficulty fixed. These are development changes; freeze them before confirmation.

This targets cascading evidence invalidation. It does not assume that a longer ledger alone will produce a useful conflict-specific failure. If clean accuracy falls too, shorten the ledger or reduce unrelated retrieval demands.

## Instructions

Cross the four contexts with three system-instruction treatments in the confirmation run:

- **None:** common rules and output format only.
- **Neutral:** a six-step block about fictional labels, terminology, and the response format. No advice about correctness, conflicts, verification, authority, or reasoning. Match the skill's token count within 2% for each model and use the same placement and formatting. It controls extra instruction length and structure; it cannot guarantee psychological inertness.
- **Skill v2:** a six-step block: identify candidate approvals; resolve withdrawals from the end backward; propagate invalidity through required evidence; discard invalid approvals; select the latest valid approval; return its route and record ID. This is an adaptation of the original skill, not a claim to test the unchanged text.

Finalize both blocks using development examples only. Give every treatment the same required JSON output. Do not demand a long written reasoning trace.

## Run plan

The updated GPT sweep requests `gpt-6-astra`, `gpt-6.1-sol`, `gpt-6-sol`, and `gpt-6-luna` at `none`, `low`, `medium`, and `high` effort. Each run snapshots the local Codex capability catalog and skips unsupported combinations with an explicit reason. The observed catalog supports low/medium/high for these models, but does not advertise `none`; low is not reasoning off. API support for `none` does not imply Codex support. Higher supported efforts can be added to a new configuration; `ultra` is excluded because it can delegate work. A cached capability entry is not a guarantee of live account access.

Use medium effort and no added instruction for each model's primary C versus RG contrast. Other effort contrasts are exploratory unless separately preregistered. These are requested model IDs through Codex, not independently verified checkpoints. Effort names are not equivalent compute budgets across models.

| Stage | Design | Calls |
|---|---|---:|
| Smoke check | 5 hand-verified short ledgers × 4 models × 3 supported efforts | 60 |
| Development | 5 worlds × 3 depths × C/RG × 4 models × 3 efforts; no added instruction | 360 |
| Confirmation | 30 fresh worlds × C/G/R/RG × 3 instructions × 4 models × 3 efforts | 4,320 |

These counts assume all 12 pairs are advertised. `manifest.json` contains the actual count. Preparation makes no model requests; collection always requires an explicit batch bound. Use a smaller frozen model/effort matrix if this budget is too large.

Development worlds use a separate seed range. At medium effort, select the lowest depth with at least 4/5 clean successes and at most 3/5 RG successes on any configured model. This screening rule only nominates a configuration; five worlds cannot establish a result. If none qualifies, extend the predefined difficulty ladder and report all screened levels. Never select individual confirmation questions based on model failures. The default confirmation depth of 4 is a placeholder to replace after this review, not a selected result.

Freeze the chosen configuration, templates, instruction blocks, model settings, scoring, and seed range before generating the 30 confirmation worlds. Use the same worlds for both models. Include reinstatement and cancellation cases, balanced winning labels and positions, and a mix of graph shapes rather than renaming one graph repeatedly. Use one completion per cell initially; spend additional budget on new worlds before repetitions. Save responses incrementally and resume incomplete cells.

Run through a consistent interface within each model. Use fresh isolated calls with tools disabled and verify the actual tool events. Preserve complete experimental prompts, input/output usage, reported finish information, errors, timestamps, interface version, and frozen design hashes. The proposed 32,000-token generation allowance is **not enforced** by this implementation because no verified Codex CLI output-token cap is available. The per-attempt 900-second timeout is a wall-clock bound, not a token bound. A visible continuation, context-compaction event, tool call, or multiple completed turns excludes the attempt; unreported internal processing cannot be ruled out. Estimate token consumption from smoke/development calls before the confirmation batch; no dollar estimate is assumed here.

## Token tracking

Track **input and output tokens for every attempt**, including smoke tests,
failed attempts, and retries. Link each usage record to its trial ID, attempt ID,
world, stage, context condition, instruction treatment, model, reasoning effort,
interface version, and completion status. Save usage incrementally alongside the
raw response; do not overwrite an earlier attempt's usage when retrying.

| Field | What to save |
|---|---|
| `input_tokens` | Input usage reported by the interface, including any additional context it counts |
| `output_tokens` | Output usage reported by the interface; preserve its native definition |
| `cached_input_tokens` | Cached input usage, when reported |
| `cache_write_input_tokens` | Cache-write input usage, when reported |
| `reasoning_output_tokens` | Reasoning-token usage, when reported; this is a count, not a reasoning transcript |
| `experimental_prompt_tokens` | Count for the saved experimental prompt, with tokenizer/version and an exact-versus-estimated flag |
| `usage_raw` | Original usage object and source event, retained for auditing the normalized fields |

The batch collector exports one row per attempt to `token_usage.csv`, including
the raw usage objects from `events.jsonl`. It normalizes a single completed
turn's usage only; multiple or ambiguous usage events remain available as raw
data with null normalized counts. The original one-example starter preserves
raw events only. Never add cumulative usage to its component events.

Missing usage must be `null`, not zero. Record the reason, such as an interrupted
run with no usage event. Preserve any known usage for failed or excluded attempts
and report usage coverage. Do not replace reported input usage with a local
prompt estimate or count only the visible JSON answer as output usage.

Document each interface's accounting rules before comparing models. Cached input
and reasoning output may already be included in the input/output totals; do not
add those fields again without verifying their definitions. Keep model-native
counts alongside normalized fields. Audit unexpectedly large input usage before
confirmation, since added instructions, tools, or other context can affect both
the token budget and the experiment.

Report total input and output tokens, plus mean and median tokens per attempt,
grouped by model, stage, context condition, instruction treatment, and reasoning
effort. Show input/output usage alongside accuracy and matched condition changes.
Report all-attempt consumption separately from the attempts included in the
accuracy analysis, and label totals as incomplete if usage is missing. For
subscription-based Codex runs, report tokens and plan-limit interruptions; do not
convert API token prices into a claimed subscription charge.

## Scoring and analysis

Parse only the designated final JSON object. Do not search the explanation for the correct route. Save separate outcomes for wrong route, wrong approval ID, route/ID mismatch, abstention, missing/malformed output, output-limit exhaustion, and execution failure.

The primary score is a completed, correctly formatted response with both the correct route and correct winning approval ID. Also report route-only accuracy and completion/format rates. An invalid returned approval ID is evidence about the selected record, not proof of the model's internal reasoning. Matching a rumor label alone is not proof that the model adopted the rumor.

Predeclare C versus RG without added instruction at medium effort as the primary contrast for each model. Secondary comparisons are C versus G, C versus R, and R versus RG. The collector reports paired world-level accuracy gaps and 95% percentile bootstrap intervals from 2,000 world resamples, using only complete eligible pairs within each contrast. It also reports effort and instruction contrasts; positive gaps mean left minus right in each CSV. Intervals are descriptive and unadjusted. It does not run significance tests or declare a break automatically. If adding significance tests, use exact paired tests and adjust across all configured model-level primary tests; label remaining comparisons exploratory.

Define an operational break on confirmation data as all of:

- C accuracy at least 90% (at least 27/30).
- RG accuracy at most 60% (at most 18/30).
- At least a 30-percentage-point paired accuracy gap, with its 95% interval excluding zero.
- At least 95% of responses in each primary cell finish with valid-format output, so the result is not mainly an output-limit or formatting failure.

These are proposed study thresholds, not an established definition of “broken.” Report results for each model separately; one failing model does not establish a failure across frontier LLMs. If clean performance is poor, classify it as general task difficulty. If failures mainly disappear at higher effort, report an effort-sensitive limitation.

For the skill, compare Skill v2 against both None and Neutral within each context. Show clean-condition changes alongside conflict-condition changes; an interaction alone can improve because the skill hurts clean accuracy. Claim a repeatable skill benefit only after confirmation supports it. Do not infer that the mechanism is unique to the checklist merely because Skill beats None.

## Validation before model collection

Implement two independent answer solvers: a reverse-pass withdrawal resolver followed by topological evidence validation, and a recursive reference evaluator on small ledgers. Agree on hand-worked cases for single withdrawals, withdrawals of withdrawals, invalid dependencies, shared evidence, reinstatement, and the final-approval tie rule.

Check that C/G/R/RG resolve to identical answers, that zero summaries means zero misleading summaries, and that C/G contain no effective revocation or invalid dependent approval. Check that retained valid evidence has no removed requirement. Test source-authority violations and ensure every reference exists and points backward. Evaluate simple shortcuts such as picking the latest approval or most repeated route, and report their accuracy on the generated set.

Use new run directories under this experiment, such as `eda/jeremy/experiment_2/results/evidence_v2_dev` and `eda/jeremy/experiment_2/results/evidence_v2_confirm` (relative to the repository root). The completed v1 datasets and labels are preserved in `eda/jeremy/experiment_1/results/`. Reuse Jeremy's frozen manifests, incremental collection, and matched analysis pattern. Kimi's current generator requires gossip and withdrawals even when rates are zero, so it needs explicit zero-condition support before being reused.

## Optional later extension: persistence across turns

After the single-turn experiment is understood, append three non-authoritative summaries without changing any official facts and ask again after each turn. Compare against matched harmless follow-ups. Measure correct-to-wrong transitions and recovery after an explicit request to recheck the ledger. Use separate sessions per condition and analyze the full trajectory as one world. This would test conversational persistence; the primary experiment above does not measure drift.
