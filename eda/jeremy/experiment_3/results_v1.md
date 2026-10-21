# Experiment 3: baseline and misleading-message isolation results

Reviewed October 21, 2026. The planned baseline/isolation stage is complete: 90 development trials, 60 combined-conflict confirmation trials, and 60 misleading-message isolation trials. These are three separate stages and are not pooled for inference. The five tiny smoke examples are excluded.

## Main finding

Astra at high reasoning made errors on dense budget ledgers, including ledgers without misleading messages. The combined-conflict comparison showed lower accuracy than clean inputs, but missed its full predeclared confirmation threshold. The subsequent isolation comparison did **not** demonstrate an additional exact-answer accuracy penalty from misleading messages when budget adjustments and withdrawals were held fixed.

This does not show that misleading messages help, are harmless, or have no effect. The isolation estimate is uncertain, and numerical errors and abstentions changed differently. A conflict-resolution skill was not tested.

## Task and stages

Each long scenario contains 3,200 records. The model must resolve withdrawals, including withdrawals of withdrawals, and calculate the opening budget plus every surviving adjustment. Unofficial messages cannot change the correct budget. Each paired version has the same answer, verified by two independent solvers. Calls use fresh sessions, no tools, and common task instructions without an added skill.

The 90-trial development screen used five worlds, three models, three reasoning settings, and C/RG. It produced 36 correct answers, two wrong budgets, and 52 abstentions. Astra-high was selected after scoring 5/5 clean and 3/5 combined-conflict. The development prompts had roughly 20% differences in reported input length, so their clean/conflict contrast cannot isolate the conflict content. See the [development report](results/flagship_dense_v1/medium_vs_high_comparison.md).

The two follow-ups used separate fresh sets of 30 paired worlds, locally token-matched inputs, and mandatory live checks that reported input counts differed by at most 2% within a pair. Neither follow-up tested added skills.

## Combined-conflict confirmation: seeds 400000–400029

| Condition | Correct | Wrong budget | Abstained | Accuracy |
|---|---:|---:|---:|---:|
| C: clean | 30 | 0 | 0 | 100% |
| RG: withdrawals and misleading messages | 22 | 6 | 2 | 73.3% |

The paired C-minus-RG accuracy gap was **26.7 percentage points**, with a 95% paired bootstrap interval of **13.3 to 43.3 points**. All 60 responses were eligible and correctly formatted; all 30 reported input-length pairs passed, with a maximum gap of about 0.54%.

The full frozen confirmation rule was **not met**. Clean accuracy passed the required 27/30, but RG was 22/30 rather than at most 18/30, and the observed gap was below the required 30 points. The interval excluded zero, but that alone did not satisfy the full rule. The thresholds have not been changed after seeing results.

This comparison jointly changes withdrawal processing, invalid alternatives, and misleading messages. It supports an observed combined-task accuracy drop, not an isolated misleading-message effect.

Sources: [summary](results/confirmation_astra_high_v1/summary.csv), [paired comparison](results/confirmation_astra_high_v1/paired_effects.csv), [input audit](results/confirmation_astra_high_v1/input_length_audit.csv), and the frozen [manifest](results/confirmation_astra_high_v1/manifest.json).

## Misleading-message isolation: seeds 500000–500029

R and RG contain identical official budget records, withdrawals, record positions, authors, unrelated messages, and correct answers. R substitutes neutral administrative notes for the 960 false unofficial messages in RG. Neutral padding balances total token counts before the final question; it does not guarantee identical token positions for every record.

| Condition | Correct | Wrong budget | Abstained | Accuracy |
|---|---:|---:|---:|---:|
| R: withdrawals only | 21 | 2 | 7 | 70% |
| RG: withdrawals and misleading messages | 24 | 4 | 2 | 80% |

The prespecified **R-minus-RG gap was -10.0 percentage points**, with a 95% paired bootstrap interval of **-33.3 to +10.0 points**. The interval uses 2,000 world resamples with seed 180. The two-sided exact paired test gave **p = 0.548828125**.

Seventeen worlds were correct in both conditions, four only in R, seven only in RG, and two incorrect in both. The exact test uses the four versus seven discordant pairs. Its result and the interval do not support a reliable difference in either direction.

The predeclared added-harm rule required a positive R-minus-RG gap, an interval entirely above zero, and exact p < 0.05, as well as complete eligible data, adequate formatting, and matching input lengths. The data-quality requirements passed; all three effect requirements failed. This was a separately frozen question, not a replacement for the earlier C/RG rule.

Outcome types matter: RG had fewer abstentions (2 versus 7) but more wrong numerical answers (4 versus 2). Those small descriptive counts do not establish a separate effect on numerical-error risk or reveal an internal mechanism. Primary accuracy counted both abstentions and wrong budgets as incorrect. There is no evidence here of a reliable accuracy improvement, despite RG's higher point estimate.

Sources: [summary](results/isolation_astra_high_v1/summary.csv), [all scores](results/isolation_astra_high_v1/scored.csv), [paired comparison](results/isolation_astra_high_v1/paired_effects.csv), [frozen plan](results/isolation_astra_high_v1/manifest.json), and [completed validation](results/isolation_astra_high_v1/post_collection_validation.json).

## Isolation validation and resource use

All 60 trials completed in one attempt each, with no missing trials, invalid output formats, tool events, or execution/interface exclusions. The audit independently checked raw responses and events against receipts and saved scores, frozen prompts and policies, requested model/effort settings, runtime consistency, source and input hashes, both answer solvers, and the R/RG message-only manipulation. Paired statistics were reproduced, including an independent exact-test calculation.

All 30 reported input-length pairs passed. The maximum gap was **0.0090%**, below the 2% limit. The run used the frozen `codex-cli 0.163.0-alpha.10.2` runtime and requested `gpt-6-astra` at `high` effort.

Collection took **6 hours 43 seconds** from first attempt start to last attempt finish, including gaps between attempts. Reported usage was **3,990,698 input tokens** and **1,142,657 output tokens**. The **1,141,956 reasoning-output tokens** are a separately reported component and are not added again to output totals.

The requested model alias does not independently verify a served checkpoint. The per-attempt 900-second timeout is enforced; the requested output-token cap is not enforced. Token matching and checks do not make the neutral text psychologically inert or identify the model's reasoning process.

## Interpretation and stopping point

The baseline/isolation stage is finished. No further collection is required to report these results. There is no demonstrated misleading-message accuracy penalty to describe as recovered by a skill.

Errors and abstentions in R show that failures occur without misleading messages. However, this does not prove that withdrawals alone caused the earlier C/RG gap: the two follow-ups used different worlds, and the isolation run has no matched clean condition. Comparisons across those runs are contextual, not a new paired causal contrast.

The results are limited to this generator, sample size, model setting, and interface. They do not establish equivalence between R and RG. A skill/neutral/no-skill comparison would be a separate future study with a new frozen plan; its outcome should not be assumed from these baselines.
