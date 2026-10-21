# Experiment 3: completed low, medium, and high reasoning comparison

Five paired worlds per condition; 3,200 records per world. **All 90 planned development trials are complete and eligible**: three models, three reasoning settings, and two conditions. These are the same five development worlds across models and efforts, not 90 independent worlds. The aggregate outcomes are 36 correct answers, two wrong budgets, and 52 abstentions. All trials used the common task rules with **no added conflict-resolution skill**.

Collection for this frozen development run is finished. Fresh-world confirmation, isolation of misleading-message effects, and testing the skill remain future work. The filename is retained for existing links; the comparison now includes low reasoning.

RG means withdrawals plus misleading messages; C is the clean control.

| Model | Reasoning | Condition | Correct | Wrong budget | Abstained | Input tokens | Output tokens |
|---|---|---|---:|---:|---:|---:|---:|
| GPT-6 Astra | Low | C | 4/5 | 0 | 1 | 285,842 | 21,283 |
| GPT-6 Astra | Low | RG | 0/5 | 0 | 5 | 342,889 | 222 |
| GPT-6 Astra | Medium | C | 4/5 | 1 | 0 | 285,834 | 26,598 |
| GPT-6 Astra | Medium | RG | 0/5 | 0 | 5 | 342,893 | 294 |
| GPT-6 Astra | High | C | 5/5 | 0 | 0 | 285,840 | 63,753 |
| GPT-6 Astra | High | RG | 3/5 | 1 | 1 | 342,897 | 88,461 |
| GPT-6.1 Sol | Low | C | 4/5 | 0 | 1 | 289,354 | 21,003 |
| GPT-6.1 Sol | Low | RG | 0/5 | 0 | 5 | 346,413 | 247 |
| GPT-6.1 Sol | Medium | C | 5/5 | 0 | 0 | 289,354 | 32,165 |
| GPT-6.1 Sol | Medium | RG | 1/5 | 0 | 4 | 346,415 | 15,987 |
| GPT-6.1 Sol | High | C | 5/5 | 0 | 0 | 289,350 | 76,546 |
| GPT-6.1 Sol | High | RG | 5/5 | 0 | 0 | 346,409 | 148,965 |
| GPT-6 Sol | Low | C | 0/5 | 0 | 5 | 285,834 | 233 |
| GPT-6 Sol | Low | RG | 0/5 | 0 | 5 | 342,887 | 115 |
| GPT-6 Sol | Medium | C | 0/5 | 0 | 5 | 285,838 | 8,407 |
| GPT-6 Sol | Medium | RG | 0/5 | 0 | 5 | 342,893 | 308 |
| GPT-6 Sol | High | C | 0/5 | 0 | 5 | 285,830 | 1,357 |
| GPT-6 Sol | High | RG | 0/5 | 0 | 5 | 342,893 | 413 |

- Correct, wrong-budget, and abstention counts use eligible final attempts. Every cell has five eligible responses and no format failures.
- Token values are reported totals for the five completed, eligible attempts in each cell. Astra's high-clean cell also had two earlier interrupted attempts with **no reported usage**. Thus these numbers are not a complete account of all consumed tokens; missing usage is not zero. The collector's all-attempt known totals happen to match the completed-attempt totals because those interruptions reported no counts.
- Reasoning-output tokens are retained separately and are not added again to output totals.

## What the final low-reasoning batch added

The 30 new low trials produced **eight correct answers, 22 abstentions, and no wrong numerical answers**. There were no retries, execution errors, tool events, or format failures in this batch.

Astra and GPT-6.1 Sol each solved four of five clean cases and abstained on all five RG cases. Their clean abstentions occurred on different worlds: Astra on `s300002_n3200`, GPT-6.1 Sol on `s300001_n3200`. GPT-6 Sol abstained on all ten low cases.

Astra's low and medium clean accuracy are both 4/5, but the failure types differ: low abstained on one case, while medium gave a wrong budget on another. Reporting accuracy alone would hide that distinction. Low is a supported reasoning setting, not reasoning off.

## Astra: higher accuracy, with one remaining numerical error

Clean accuracy increased from **80% to 100%**. High reasoning corrected the medium error on `s300004_n3200`, returning the correct $2,365K rather than $2,470K. The other four clean answers remained correct.

Conflict accuracy increased from **0% to 60%**. Three medium abstentions became correct answers, one became a wrong numerical answer, and one remained an abstention:

| World | Correct budget, K | Medium conflict response | High conflict response | High outcome |
|---|---:|---|---|---|
| s300000_n3200 | -830 | ABSTAIN | $-830K | Correct |
| s300001_n3200 | 20 | ABSTAIN | $30K | Wrong budget, +$10K |
| s300002_n3200 | 1595 | ABSTAIN | $1595K | Correct |
| s300003_n3200 | 1315 | ABSTAIN | ABSTAIN | Abstained |
| s300004_n3200 | 2365 | ABSTAIN | $2365K | Correct |

This is a verified flagship numerical error even at high reasoning. It does not establish how the model arrived at that number or that it adopted a misleading claim. High reasoning improved observed performance but did not eliminate all failures. High is not the maximum advertised effort.

## GPT-6.1 Sol: all ten high-reasoning answers correct

Clean accuracy stayed at **5/5**. RG accuracy increased from **1/5 to 5/5**: all four medium-reasoning abstentions became correct answers, and the previously correct RG answer remained correct. There are no wrong budgets, abstentions, or format failures at high reasoning on these five paired worlds.

| World | Correct budget, K | Medium RG response | High RG response |
|---|---:|---|---|
| s300000_n3200 | -830 | $-830K | $-830K |
| s300001_n3200 | 20 | ABSTAIN | $20K |
| s300002_n3200 | 1595 | ABSTAIN | $1595K |
| s300003_n3200 | 1315 | ABSTAIN | $1315K |
| s300004_n3200 | 2365 | ABSTAIN | $2365K |

Higher reasoning helped this model on the observed task. The result differs from Luna's approval-task pattern, where higher reasoning reduced abstentions without improving conflict accuracy. Neither observation supports a universal claim that additional reasoning always helps or never helps.

## GPT-6 Sol: abstentions at every tested setting

All 30 responses across low, medium, and high are explicit `ANSWER: ABSTAIN`. There are no wrong numerical answers. Because the model also abstains on every clean case, this does not isolate a conflict-specific failure. The saved terminal answers do not explain the abstentions.

The high setting used fewer output tokens than medium overall, despite the requested effort increase. One medium clean attempt used 8,061 output tokens before abstaining, while every high response was short. Requested effort is a setting, not a guaranteed minimum amount of output or reasoning.

## Token and time comparison

| Model | Effort | Completed trials | Input tokens | Output tokens | Reasoning-output tokens | Summed elapsed time of completed attempts |
|---|---|---:|---:|---:|---:|---:|
| GPT-6 Astra | Low | 10 | 628,731 | 21,505 | 21,392 | 6m 46s |
| GPT-6 Astra | Medium | 10 | 628,727 | 26,892 | 26,778 | 7m 54s |
| GPT-6 Astra | High | 10 | 628,737 | 152,214 | 152,097 | 38m 44s |
| GPT-6.1 Sol | Low | 10 | 635,767 | 21,250 | 21,136 | 5m 21s |
| GPT-6.1 Sol | Medium | 10 | 635,769 | 48,152 | 48,037 | 10m 13s |
| GPT-6.1 Sol | High | 10 | 635,759 | 225,511 | 225,393 | 44m 30s |
| GPT-6 Sol | Low | 10 | 628,721 | 348 | 244 | 1m 6s |
| GPT-6 Sol | Medium | 10 | 628,731 | 8,715 | 8,605 | 2m 27s |
| GPT-6 Sol | High | 10 | 628,723 | 1,770 | 1,660 | 1m 15s |

On completed attempts, Astra-high used **5.66 times as many output tokens** as medium and improved overall accuracy from 4/10 to 8/10. GPT-6.1 Sol-high used **4.68 times as many output tokens**, improving from 6/10 to 10/10. Their respective input totals differed by only ten tokens across the same questions. Elapsed totals sum individual attempt durations; they exclude gaps between collection sessions. The two interrupted Astra-high attempts consumed another 89.373 seconds, but their token usage is unknown.

The 20 Sol-high attempts used **1,264,482 input tokens and 227,281 output tokens**, including 227,053 reasoning-output tokens, over 45m 45s of summed attempt time. These attempts all completed successfully without retries.

The final 30 low attempts used **1,893,219 input tokens and 43,103 output tokens**, including 42,772 reasoning-output tokens, over 13m 14s of summed attempt time.

Across all 90 completed trials, reported totals are **5,679,665 input tokens and 506,357 output tokens**, including 505,342 reasoning-output tokens. Completed attempts took 1h 58m 16s in total, excluding gaps between sessions and the two earlier interrupted attempts. Their unknown token usage remains excluded, not counted as zero.

GPT-6.1 Sol's `s300003_n3200` RG attempt reported **41,920 output tokens**. The CLI does not enforce the originally requested 32,000-token cap, so these are comparisons of requested effort settings, not comparisons under a fixed output-token budget. That response completed normally and is not a timeout or truncated answer.

The differences in output use partly reflect how often each setting produced short abstentions. Token use is an observed cost of the settings and outcomes, not proof of an internal reasoning mechanism.

## Validation and limits

Frozen source and input hashes were checked. All 92 saved attempts were audited against their raw response files, event streams, frozen prompts/policies, and requested model/effort commands. The 90 latest outcomes reproduce exactly, and both independent solvers agree on all five world keys in every generated condition. Each included trial has one fresh completed turn, one final message, and no tool or error events. The final Astra-high retry on `s300003_n3200` clean succeeded; its earlier interruptions are preserved separately.

The current data support an effort comparison within each condition because the prompts stay fixed. However, conflict prompts used **18.6%–21.4% more reported input tokens** than clean prompts. C/RG also changes withdrawal processing and invalid alternatives as well as misleading messages. The clean-versus-conflict difference therefore does not isolate misleading information alone, and five worlds are an exploratory sample. A confirmed causal claim about misleading records requires a new plan with improved token matching, fresh worlds, and separate controls for withdrawals and misleading messages. Model aliases are requested through Codex; the event streams do not independently identify a served checkpoint.

## Recommended next stage

There are no unfinished trials in this run. Repeating the completed collection commands adds no new data. Preserve the frozen prompts and all outcomes, including abstentions and wrong answers.

**Astra at high reasoning is the recommended candidate for a separate confirmation run**, because it solved all five clean cases but still produced one wrong budget and one abstention in RG. This is an exploratory selection from the development results, not a confirmed failure rate. GPT-6.1 Sol-high solved every case, while GPT-6 Sol's clean abstentions make it less useful for isolating a conflict effect at this difficulty.

Before collecting confirmation data, correct and validate condition token matching in a separate run. The current character-based estimate is inadequate; do not label a tokenizer exact for a requested model without verification. Keep record positions, valid adjustments, answer keys, task rules, and the no-tool setup fixed across paired conditions. Any calibration calls should be marked as calibration and kept out of confirmation scoring.

The existing study plan calls for **30 fresh paired worlds starting at seed 400000**, one selected model/effort, and C/RG with no added skill: 60 eligible responses. Freeze the revised configuration before collection and report it separately from development. Retain the planned confirmation criteria: C at least 27/30, RG at most 18/30, a paired accuracy gap of at least 30 percentage points with its 95% interval excluding zero, and at least 29/30 valid-format responses per condition. Continue to separate wrong budgets from abstentions.

This first confirmation would test the combined conflict task. To connect a reproducible effect specifically to misleading information, follow with withdrawal-only and misleading-message-only controls. In particular, R versus RG keeps withdrawals present while adding misleading messages. Then compare no added skill, a neutral instruction of similar length and format, and the conflict-resolution checklist at a fixed reasoning setting. Include clean/control conditions so that a general accuracy improvement is not mislabeled as resistance to misleading information. These skill and isolation comparisons have not been collected here.

No new run or model calls were started during this review.

Sources: `progress.json`, `summary.csv`, `scored.csv`, `token_usage.csv`, `reasoning_effects.csv`, frozen worlds, and the per-attempt receipts, responses, and event streams in this run. Updated after all 30 low trials completed; this comparison is not automatically updated by the collector.
