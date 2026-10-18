# Development v1: medium-effort findings

All 120 planned medium-effort trials completed and passed the event audit. Recomputed scores agree with the saved results; both independent solvers agree on every frozen world and context. Low/high trials remain uncollected.

## Accuracy

C = clean; RG = revoked evidence plus misleading team summaries. Each entry is correct responses out of five worlds. Depths reuse the same five seed indices, so pooled depth totals are not 15 independent worlds.

| Model | Depth | C | RG | C minus RG (percentage points) |
|---|---:|---:|---:|---:|
| gpt-6-astra | 2 | 5/5 | 5/5 | 0 |
| gpt-6-astra | 4 | 5/5 | 5/5 | 0 |
| gpt-6-astra | 8 | 5/5 | 5/5 | 0 |
| gpt-6.1-sol | 2 | 5/5 | 5/5 | 0 |
| gpt-6.1-sol | 4 | 5/5 | 5/5 | 0 |
| gpt-6.1-sol | 8 | 5/5 | 5/5 | 0 |
| gpt-6-sol | 2 | 5/5 | 5/5 | 0 |
| gpt-6-sol | 4 | 5/5 | 5/5 | 0 |
| gpt-6-sol | 8 | 5/5 | 5/5 | 0 |
| gpt-6-luna | 2 | 1/5 | 1/5 | 0 |
| gpt-6-luna | 4 | 3/5 | 0/5 | 60 |
| gpt-6-luna | 8 | 3/5 | 1/5 | 40 |

Overall: 99/120 exact answers, 16 wrong routes, 2 wrong approval IDs, and 3 abstentions. All 21 non-correct answers came from GPT-6 Luna.

## Interpretation and decision

No model/depth meets the predeclared development screen: at least 4/5 clean successes and at most 3/5 RG successes. Astra, GPT-6.1 Sol, and GPT-6 Sol are at ceiling on this sample. Luna shows an additional RG penalty at depths 4 and 8, but its clean accuracy of 1/5, 3/5, and 3/5 falls below the control threshold. This is preliminary evidence of general task difficulty for Luna, with a possible additional conflict effect; it does not establish a reliable frontier-wide failure.

The next screen follows the planned difficulty ladder: depth 16 at 1,600 records, with 20 projects, eight candidate approvals, eight summary slots, and the same five development seeds. Keep all four models to show the full screen. Start with medium effort: 5 worlds × 2 contexts × 4 models = 40 new calls. The separately frozen plan retains low/high as available later comparisons. This prioritizes difficulty calibration before completing the remaining 240 low/high trials in the original run.

If depth 16 still leaves the stronger models at ceiling, review before extending to 3,200 records. Luna needs an easier control in any separate Luna-focused follow-up. No confirmation depth has been selected, and no confirmation calls should be inferred from this report.

## Token accounting and limits

Reported across all 120 medium attempts: **5,225,410 input tokens**, **16,756 output tokens**, and 14,558 reasoning-output tokens reported separately. All 120 attempts reported each of these fields. Reasoning tokens are not added again to output totals.

Input includes Codex overhead. Counts used to match experimental prompts remain character-based estimates; actual token equivalence is unverified. The interface does not enforce the proposed 32,000-output-token cap. Model IDs are requested Codex aliases, not pinned independently verified checkpoints. The five-world development screen and unadjusted bootstrap intervals are exploratory; perfect observed performance does not imply a zero population error rate.

Sources: `manifest.json`, `worlds.jsonl`, `responses.jsonl`, `summary.csv`, `paired_effects.csv`, and `token_usage.csv` in this run. Existing raw attempts and frozen files were preserved.
