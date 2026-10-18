# Astra medium: first ten dense-ledger trials

All ten scheduled Astra-medium trials completed and passed the event audit. The five short smoke trials also passed. No new model requests were made during this review.

The frozen source and artifact hashes were verified. Each saved prompt and policy matches its frozen input. Raw final-response files and event streams match their receipts, and rescoring reproduces the saved outcomes. Both independent answer solvers agree on all five world keys in all four generated conditions. The run currently has 10 of 90 planned trials collected; the remaining 80 belong to other model/effort cells.

## Observed results

| Condition | Correct | Wrong budget | Abstained | Format failures | Eligible |
|---|---:|---:|---:|---:|---:|
| C: clean | 4/5 | 1/5 | 0/5 | 0/5 | 5/5 |
| RG: withdrawals and misleading messages | 0/5 | 0/5 | 5/5 | 0/5 | 5/5 |

Astra produced one verified incorrect numerical answer, on a **clean** ledger. On `s300004_n3200`, it returned `ANSWER: $2470K`; both solvers give `ANSWER: $2365K`, a difference of **+$105K**. This is an observed flagship error on dense accounting. It is not evidence that the misleading messages caused that error: there were no misleading messages in that condition.

Every RG response was exactly `ANSWER: ABSTAIN`. Those are unsuccessful task answers and count as not correct in exact accuracy, but they are not false numerical claims, timeouts, or formatting errors. The final responses contain no explanation of the abstentions. Their internal cause cannot be inferred from these outputs alone.

| World | Correct budget, K | Clean response, K | Conflict response |
|---|---:|---:|---|
| s300000_n3200 | -830 | -830 | ABSTAIN |
| s300001_n3200 | 20 | 20 | ABSTAIN |
| s300002_n3200 | 1595 | 1595 | ABSTAIN |
| s300003_n3200 | 1315 | 1315 | ABSTAIN |
| s300004_n3200 | 2365 | 2470 | ABSTAIN |

The observed exact-accuracy gap is 80 percentage points. This meets the exploratory count-based screening rule, but five worlds and the token-length imbalance below do not support a confirmed causal claim about misinformation. There is no numerical answer in RG to compare with a rumor's claimed budget.

## Token use and the length-matching limitation

| Condition | Reported input | Reported output | Reported reasoning output | Mean output per trial |
|---|---:|---:|---:|---:|
| C | 285,834 | 26,598 | 26,539 | 5,319.6 |
| RG | 342,893 | 294 | 239 | 58.8 |
| Total | **628,727** | **26,892** | **26,778** | 2,689.2 |

Reasoning output is retained separately and is not added again to output totals. All ten attempts report usage. Cached input is also retained separately in the original token table. The very low RG output counts are consistent with the short abstentions; they are not evidence of a runtime or output-limit failure. All ten have one fresh thread, one completed turn, one final message, no tool events, and no error events. The served model is not independently reported in these streams; the requested alias is saved.

**The character-based matching did not produce matched actual input-token counts.** RG used 18.81%–21.39% more input tokens than its paired clean prompt (19.96% more in aggregate). This exceeds the intended 2% tolerance. Specifically:

| World | Clean input tokens | Conflict input tokens | Conflict increase over clean |
|---|---:|---:|---:|
| s300000_n3200 | 57,412 | 69,693 | 21.39% |
| s300001_n3200 | 57,049 | 67,778 | 18.81% |
| s300002_n3200 | 57,209 | 68,766 | 20.20% |
| s300003_n3200 | 56,979 | 67,865 | 19.11% |
| s300004_n3200 | 57,185 | 68,791 | 20.30% |

Both variants still contain 3,200 records and the same surviving adjustments. However, actual input length differs alongside the withdrawal and gossip treatments. The C/RG result is therefore exploratory and confounded with input length. Before a causal confirmation study, use a new frozen run with improved token matching validated against reported usage. Preserve this run and report the limitation rather than editing its prompts or rerunning its completed answers.

## Next collection

For the user's focus on flagship robustness, run the already planned **ten Astra-high trials** on these same five C/RG pairs:

```bash
python3 run.py collect --run results/flagship_dense_v1 --models gpt-6-astra --efforts high --max-new-trials 10
```

This tests whether increased reasoning effort fixes the clean arithmetic error and changes the conflict abstentions. It retains the same prompts within each condition, allowing a matched effort comparison. It does not repair the C/RG input-length difference. High is not the maximum advertised effort. Collect all ten, including cases where medium was correct; do not select only the failed prompt.

Then finish the primary medium screen on both Sol models:

```bash
python3 run.py collect --run results/flagship_dense_v1 --efforts medium --max-new-trials 20
```

The completed ten Astra-medium trials will be skipped. These are existing planned cells; no prompts or scoring rules need to change. A setting that keeps producing verified wrong numerical answers is a candidate for fresh-world replication. A setting that abstains should be reported as abstaining, not as generating misinformation. Do not launch the fresh-world causal confirmation until the input-length issue is addressed in a separate plan.

Sources: this run's frozen manifest, worlds, prompts, per-attempt response files and events, `summary.csv`, `token_usage.csv`, and `paired_effects.csv`. The incorrect response is saved at `attempts/2664fef3183c46229ab5/001/response.txt`.
