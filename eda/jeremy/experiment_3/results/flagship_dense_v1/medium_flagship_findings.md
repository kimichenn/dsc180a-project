# Experiment 3: completed medium-reasoning screen

All 30 medium-reasoning trials are complete: three models, five paired worlds, and two conditions. The latest batch added 20 Sol trials, with **six correct answers, fourteen abstentions, and no wrong numerical answers**. All 20 were eligible and validly formatted, with no tool use or execution errors.

## Results

C is the clean ledger. RG contains withdrawals plus misleading unofficial messages. Counts use the same five worlds in each cell; these are paired comparisons, not independent sets of worlds.

| Model, medium reasoning | Clean correct | Clean wrong budget | Clean abstained | RG correct | RG wrong budget | RG abstained |
|---|---:|---:|---:|---:|---:|---:|
| GPT-6 Astra | 4/5 | 1 | 0 | 0/5 | 0 | 5 |
| GPT-6.1 Sol | 5/5 | 0 | 0 | 1/5 | 0 | 4 |
| GPT-6 Sol | 0/5 | 0 | 5 | 0/5 | 0 | 5 |

GPT-6.1 Sol shows an exploratory clean-versus-conflict difference: it can solve every clean case at medium reasoning, but abstains on four of five RG cases. Its one correct RG response is `s300000_n3200`, returning `ANSWER: $-830K`. An abstention means the model explicitly returned `ANSWER: ABSTAIN`; it did not supply an incorrect budget.

GPT-6 Sol abstains even on the clean task. Its results therefore do not isolate a conflict-specific penalty. Most of its abstentions are short, but the clean `s300002_n3200` attempt spent 95.104 seconds and 8,061 output tokens before abstaining. Final responses alone do not establish why a model abstained.

The only wrong numerical answer in the medium screen remains Astra's clean `s300004_n3200` response: $2,470K instead of $2,365K. Astra also previously produced one wrong RG budget at high reasoning; see the [Astra medium-versus-high comparison](medium_vs_high_comparison.md).

## Reported token usage

Totals below cover ten eligible medium attempts per model. Reasoning-output tokens are a component of reported output, not an additional amount to add to it.

| Model | Input tokens | Output tokens | Reasoning-output tokens |
|---|---:|---:|---:|
| GPT-6 Astra | 628,727 | 26,892 | 26,778 |
| GPT-6.1 Sol | 635,769 | 48,152 | 48,037 |
| GPT-6 Sol | 628,731 | 8,715 | 8,605 |
| All medium trials | 1,893,227 | 83,759 | 83,420 |

The latest 20 Sol trials used **1,264,500 input tokens and 56,867 output tokens**. The small output total for GPT-6 Sol reflects its abstentions and should not be interpreted as efficiency at successfully solving the task.

## Validation and limits

Frozen source and artifact hashes were verified. Saved responses and event streams reproduce the outcomes in `scored.csv`; attempt prompts and policies match the frozen inputs. Every medium trial contains one fresh completed turn with no tool or error events. The two independent answer solvers agree on all five worlds in every generated condition.

Each cell contains only five worlds. Across medium trials, RG inputs used approximately **18.6%–21.4% more reported input tokens** than their paired clean inputs, despite the original character-based length matching. Thus the C/RG accuracy differences do not establish that misleading messages alone caused the failures: input length and withdrawal processing also differ. A causal confirmation requires improved token matching in a separate frozen run, fresh worlds, and subsequent withdrawal-only and misleading-message-only comparisons as appropriate.

The within-condition medium-versus-high comparison keeps the task prompts fixed and is the next planned step. Model aliases identify the requested models, not independently verified served checkpoints.

## Next batch

Collect the two Sol models at high reasoning on the same five C/RG pairs: **20 new trials**. From the Experiment 3 directory:

```bash
python3 run.py collect --run results/flagship_dense_v1 --models gpt-6.1-sol gpt-6-sol --efforts high --max-new-trials 20
```

This checks whether GPT-6.1 Sol's RG abstentions become correct or wrong answers, and whether GPT-6 Sol can solve the clean task with higher reasoning effort. Complete all cells rather than stopping after the first error; preserve completed abstentions and wrong answers.

At this review, **40 of 90 planned trials are complete and eligible**: all 30 medium trials and ten Astra-high trials. There are 42 saved attempts because Astra-high had two earlier interruptions. Completing the next batch will bring coverage to 60/90. The remaining 30 low-reasoning trials can then finish the frozen development screen:

```bash
python3 run.py collect --run results/flagship_dense_v1 --efforts low --max-new-trials 30
```

Review the high results before moving to fresh-world confirmation. Do not change this run's saved prompts or count the five reused worlds as fresh replications.

Sources: `progress.json`, `scored.csv`, `summary.csv`, `token_usage.csv`, frozen worlds and inputs, and per-attempt receipts, responses, and event streams. This report is a snapshot after the two Sol-medium batches completed; the collector does not update it automatically.
