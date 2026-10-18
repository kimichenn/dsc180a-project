# Depth 16: medium-effort findings and comparison with Kimi

All 40 medium-effort trials completed, with 40 eligible single-turn responses. Both answer solvers agree on all five frozen worlds and their four contexts. Recomputed scores agree with all saved responses. No additional model calls were made during this review.

## Results

C = clean. RG = revocations plus misleading summaries. Each condition contains five development worlds.

| Model | C correct | RG correct | C abstentions | RG abstentions |
|---|---:|---:|---:|---:|
| gpt-6-astra | 5/5 | 5/5 | 0 | 0 |
| gpt-6.1-sol | 5/5 | 5/5 | 0 | 0 |
| gpt-6-sol | 5/5 | 5/5 | 0 | 0 |
| gpt-6-luna | 4/5 | 1/5 | 1 | 4 |

Luna is the first model/depth combination in this sweep to meet the predeclared development screen: C >= 4/5 and RG <= 3/5. Three worlds change from correct in C to abstention in RG; one is correct in both, and one is an abstention in both. All five non-correct responses explicitly return ABSTAIN in both JSON fields. There are no wrong-route or wrong-approval-ID responses in this run. The observed gap is therefore an abstention effect, not evidence that Luna adopted a false route.

This nominates depth 16 for further development and potential fresh-world confirmation. It does not establish a reproducible break: only five worlds were tested, clean accuracy is 80%, and the stronger three models remain perfect on this sample. The paired 60-point Luna gap has an unadjusted five-world bootstrap interval of 20 to 100 points; after screening several depths/models, this is descriptive rather than confirmatory evidence.

## What Kimi did differently

Live GitHub branch lookup confirmed `kimi/eda` at `977328dc52d606cb031ed7045e6e88dea1ab69f7`. I reviewed the v5 [findings](https://github.com/kimichenn/dsc180a-project/blob/977328dc52d606cb031ed7045e6e88dea1ab69f7/eda/kimi/reports/v5/findings.md), [model configuration](https://github.com/kimichenn/dsc180a-project/blob/977328dc52d606cb031ed7045e6e88dea1ab69f7/eda/kimi/config/v5_models.toml), [profile](https://github.com/kimichenn/dsc180a-project/blob/977328dc52d606cb031ed7045e6e88dea1ab69f7/eda/kimi/chain/dials.py), [long-run raw responses](https://github.com/kimichenn/dsc180a-project/blob/977328dc52d606cb031ed7045e6e88dea1ab69f7/eda/kimi/results/v5/break_P0_long/responses.jsonl), and [scored table](https://github.com/kimichenn/dsc180a-project/blob/977328dc52d606cb031ed7045e6e88dea1ab69f7/eda/kimi/results/v5/break_P0_long/scored.csv). These are v5 results; the earlier v4 review is not the evidence for the following counts.

| Difference | Kimi v5 P0 | Jeremy depth-16 run |
|---|---|---|
| Task | Compute the current budget after signed increases/decreases and withdrawals | Select the latest approval whose evidence remains valid |
| Astra effort | Low | Medium |
| Lengths compared here | 1,600 and 3,200 records | 1,600 records |
| Work that contributes to answer | 555-585 surviving budget adjustments at 1,600 records; 1,133-1,175 at 3,200 | Eight target approvals, 114 target evidence nodes, 18-21 target withdrawals; a single winning approval |
| Density | 719 budget adjustments + 240 withdrawals + 480 gossip notes at 1,600 | 1,388-1,395 of 1,600 records are messages; eight are designated misleading summaries in RG |
| Answer form | Working allowed; final ANSWER budget line | Final route/approval JSON; explicit abstention option |
| Policy placement | Task policy is in user-provided ledger text | Authority/validity rules are in the study system instructions |
| Interface | Codex subscription CLI with additional context/catalog isolation settings | Same recorded CLI version, different isolation settings and residual wrapper overhead |

Kimi kept relative_rate=1.0, so later budget resets do not erase earlier changes. The model must accumulate the surviving signed changes across the log. His recorded Astra failures were wrong totals: for example, n3200_seed1 conflict expected $1,490K and returned $1,470K. Calling an error missed_one_update is only a heuristic based on its numeric size; it does not prove which operation the model omitted.

## Kimi Astra result, independently checked

| Records | Control | Conflict |
|---|---:|---:|
| 1,600 | 4/5 | 5/5 |
| 3,200 | 3/5 | 3/5 |

Independent recomputation of effective withdrawals and budget sums agrees with all ten saved long-run gold budgets in both conditions. Parsing each saved Astra final answer reproduces the table. All 20 Astra long-run records have low effort, no reported tools, and no execution error. Across the two lengths, Astra is 7/10 control and 8/10 conflict. Its misses demonstrate failures on the task, but this sample does not show an aggregate conflict penalty for Astra.

Kimi's clearer conflict-specific result was Claude Opus: 10/10 control versus 3/10 conflict across these lengths. Arithmetic workload, reasoning effort, output format, policy placement, and harness context all differ between studies. It is plausible that cumulative arithmetic makes his task harder for Astra, but these observations do not isolate a single cause. More filler records alone do not recreate that workload.

## Next: two focused, already-planned comparisons

1. Astra at low effort on the same depth-16 worlds: ten calls, compared with the completed medium trials. This isolates the requested effort change within our task; it does not replicate Kimi's arithmetic task.
2. Luna at high effort on the same depth-16 worlds: ten calls, compared with completed medium trials. This checks whether more reasoning improves clean accuracy and reduces conflict abstentions.

From the experiment_2 folder:

```bash
python3 run.py collect --run results/development_depth16_v1 --models gpt-6-astra --efforts low --max-new-trials 10
python3 run.py collect --run results/development_depth16_v1 --models gpt-6-luna --efforts high --max-new-trials 10
```

Both sets are in the existing frozen schedule and were uncollected when this review was written. Analysis will automatically update reasoning_effects.csv. Review the paired outcomes and tokens after these twenty calls before deciding the confirmation model/effort matrix. Fresh confirmation worlds must stay separate from these development seeds, and the exact-token-matching limitation must be resolved or explicitly recorded before confirmation.

If Astra remains perfect at low effort, the focused next Astra study should compare Kimi's exact arithmetic workload at low and medium effort, or explicitly add an aggregation task with matched controls. Replaying only previously failing prompts is a diagnostic reproduction, not an unbiased new benchmark; use the full predeclared set and fresh worlds for generalization. Do not pool a changed task or harness with the existing approval experiment.

## Token usage

- input_tokens: 1,748,622, reported on all 40 attempts.
- output_tokens: 8,763, reported on all 40 attempts.
- reasoning_output_tokens: 8,022, reported on all 40 attempts.

Reasoning output is retained separately and is not added again to output totals. Input includes Codex overhead. Experimental prompt counts are character-based estimates, not verified exact token counts. The generation-token cap is not enforced; requested model IDs are not pinned served checkpoints. Raw attempts, original plans, and collector code were preserved.
