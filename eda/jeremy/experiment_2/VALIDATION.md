# Implementation validation

Verified on 2026-10-18 UTC (2026-10-17 Pacific).

27 offline tests passed, including generator invariants, independent solver agreement, strict answer parsing, missing/ambiguous token usage, interruption recovery, retry limits, frozen inputs, and paired comparisons.

Temporary preparation of the full default development and confirmation plans passed: 15 world/depth combinations and 360 trials for development; 30 worlds and 4,320 trials for confirmation. All within-world prompt estimates met the 2% tolerance. These temporary validation plans made no model calls.

## Live smoke checks

Run: [results/smoke_v2](results/smoke_v2). Six calls completed, all six correct and eligible. 54 of the 60 planned smoke trials remain. The four requested models were accessible during these checks; this is not a guarantee of future access or pinned checkpoint identity.

| Model | Effort | Question | Input tokens | Output tokens | Reasoning tokens |
|---|---|---|---:|---:|---:|
| gpt-6-astra | medium | smoke_shared_evidence | 10073 | 27 | 8 |
| gpt-6-sol | medium | smoke_single_withdrawal | 10030 | 41 | 22 |
| gpt-6-astra | high | smoke_shared_evidence | 10071 | 38 | 19 |
| gpt-6-luna | medium | smoke_clean_chain | 10012 | 16 | 0 |
| gpt-6-astra | low | smoke_shared_evidence | 10073 | 17 | 0 |
| gpt-6.1-sol | medium | smoke_clean_chain | 10718 | 28 | 10 |

Total reported usage for these six successful checks: **60,977 input tokens and 167 output tokens**. Reasoning is retained separately and not added again.

These tiny hand-worked questions validate collection, not long-context robustness. The models did not all receive the same smoke question in this initial sample. Do not interpret six successes as a comparative model or reasoning-effort result.

Every included attempt had one fresh thread, one started/completed turn, one final response, and no observed tools, error events, or unexpected events. Actual input usage was about 10,000 tokens per call, substantially above the saved experimental-text estimate. This confirms remaining Codex/service overhead; do not claim pure API prompt isolation or exact served-context reconstruction.

## Preserved integration diagnostics

`results/smoke_v1` retains one sandbox startup failure with no reported usage and one correct response excluded because an unstable-feature startup warning appeared as an error item. The collector now suppresses that known CLI warning via a per-process setting. The corrected configuration was frozen separately as `smoke_v2`; the earlier logs were not rewritten or pooled into its accuracy.

No long development or confirmation calls were made. Unsupported `none` effort combinations were skipped explicitly. Exact prompt token matching remains unverified with the default character estimate, and no 32,000-output-token cap is enforced.
