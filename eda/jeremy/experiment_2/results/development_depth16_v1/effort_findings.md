# Depth 16: Astra low and Luna high follow-up

All 20 new attempts completed and passed the event audit. The two independent answer solvers agree on the saved world keys, and recomputing the 20 final-answer scores reproduces the saved outcomes. These are the same five development worlds used at medium effort, not new independent replications.

## Accuracy and abstentions

C is clean; RG combines revocations and misleading summaries. Exact correctness requires both the route and the latest valid approval ID.

| Model | Effort | C correct | RG correct | C abstentions | RG abstentions | Input tokens, all 10 | Output tokens, all 10 |
|---|---|---:|---:|---:|---:|---:|---:|
| gpt-6-astra | low | 5/5 | 5/5 | 0 | 0 | 435,389 | 1,377 |
| gpt-6-astra | medium | 5/5 | 5/5 | 0 | 0 | 435,393 | 1,918 |
| gpt-6-luna | medium | 4/5 | 1/5 | 1 | 4 | 435,405 | 892 |
| gpt-6-luna | high | 5/5 | 1/5 | 0 | 0 | 435,393 | 9,452 |

Astra is still 10/10 at low effort. Lowering effort alone did not reproduce the failures from Kimi's different arithmetic workload. This small result does not establish universal robustness.

Luna high is 5/5 clean and 1/5 RG: an observed 80-point gap. Its four RG errors comprise three wrong routes and one correct route with the wrong approval ID. There are no high-effort abstentions. Higher effort improved the clean result by one question but did not improve aggregate RG exact accuracy.

The matched RG changes are important: s100001 changes from correct at medium to a wrong approval ID at high; s100003 changes from abstention to correct. The other three RG abstentions become wrong routes. Thus the four mistakes are not simply the same four medium-effort abstentions reappearing as errors.

## What the four high-effort RG answers selected

| World | Saved outcome | Selected record status |
|---|---|---|
| s100000_d16 | Wrong route | Invalid approval R01491 instead of R00467 |
| s100001_d16 | Wrong approval ID | Valid fallback R00452, but a later valid BLUE approval R01193 exists |
| s100002_d16 | Wrong route | Valid AMBER fallback R00117 instead of the later valid CORAL approval R01341 |
| s100004_d16 | Wrong route | Invalid approval R01441 instead of R01467 |

All four returned IDs belong to the requested project. Two errors selected invalid approvals; two selected valid but older approvals. One returned route equals the misleading summary's route. These are observable answer selections, not proof of the model's internal reasoning or of rumor adoption.

## Token comparison

Luna high used 9,452 output tokens versus 892 at medium, about 10.6 times as many across the same ten trials. Reported reasoning-output tokens were 9,265 versus 715. Reasoning usage is retained separately and is not added again to output totals. Increased output usage did not improve RG exact accuracy on this sample.

The two new batches together used 870,782 input tokens and 10,829 output tokens. All 20 attempts reported input, output, and reasoning token counts. Within each of the five Luna-high C/RG pairs, reported input usage differed by approximately 0.61%-0.90%; this is a useful runtime check, but does not establish exact prompt-token matching for future questions.

## Recommended next step

Freeze a focused, prospective follow-up: GPT-6 Luna at high effort, depth 16, 1,600 records, 30 fresh worlds (seeds 200000-200029), C versus RG, and no added instruction. This is 60 trials. The model/effort choice is selected from development and is a documented amendment to the original medium-effort, multi-model confirmation plan. The fresh-world results must not be pooled with the five development worlds.

Use the existing operational thresholds: at least 27/30 exact clean answers, at most 18/30 exact RG answers, at least a 30-point paired accuracy gap with its 95% interval excluding zero, and at least 29/30 valid-format responses per condition. Complete all 60 eligible trials before assessing these thresholds; execution failures stay separate from answer errors and require resolution or an incomplete-study report. Report wrong routes, wrong IDs, abstentions, and route-only accuracy separately.

The follow-up uses the same character-based prompt-length estimate as development. Its manifest explicitly records allow_estimated_tokens=true. Matching actual model tokens remains unverified, and actual reported input usage must be audited per pair. This limits a claim that the effect is isolated from all token-length differences. The 32,000-output-token cap remains unenforced. No new model calls were made while preparing this plan.

If the fresh-world gap holds, add the G-only and R-only conditions to distinguish summaries from revocations, then evaluate skill versus neutral and no added instruction. Those are later experiments and are not in this 60-call plan. A Luna-specific result must not be described as breaking Astra or all frontier models.

## Next command

From the experiment_2 folder, after preparation has completed:

```bash
python3 run.py collect --run results/confirmation_luna_high_v1 --max-new-trials 60
```

This runs the new 60-trial plan, skipping any already completed cells. For smaller batches use --max-new-trials 10. Based on development usage, 60 calls would be roughly 2.6 million input and 57,000 output tokens, with substantial uncertainty on new worlds; this is a token estimate, not a subscription charge.

Sources: the frozen manifest/worlds and saved per-attempt receipts, responses.jsonl, summary.csv, and reasoning_effects.csv in this run. Original prompts, responses, and collection code were preserved.
