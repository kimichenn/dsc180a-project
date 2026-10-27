# Minimal checklist v2: failure review

Reviewed all 60 minimal-v2 responses and their matched no-skill conditions from the completed 360-call screen. All 11 minimal-v2 failures produced numeric answers; these were completed, eligible calls. This review uses final responses and deterministic source-record checks, not inferred internal reasoning.

| Version | No skill correct / 15 | Minimal v2 correct / 15 |
| --- | ---: | ---: |
| C | 15/15 | 14/15 |
| R | 12/15 | 10/15 |
| RG | 10/15 | 13/15 |
| E | 12/15 | 12/15 |

Both conditions scored 49/60 overall. Minimal v2 gained one correct response across R/RG and lost one across C/E. Its R/RG per-log gains were -10, -10, and +30 percentage points. Three independent logs do not establish a repeatable improvement.

## What the visible failures establish

Four failures occurred in C or E, where the presented records contain no withdrawal chains: one clean failure and three explicit-reversal failures. Those errors therefore do not require a withdrawal-resolution mistake. They could reflect record selection, an incorrect operation, or arithmetic; a final total alone does not distinguish these.

Three wrong responses included checkpoint tables. Comparing those checkpoints with the exact records gives:

- In s730000 R repeat 4, all seven reported checkpoints through record 1400 exactly matched the prefixes of the globally effective updates. Only the last checkpoint was wrong: 1486 rather than 1491. This localizes the visible divergence to the last reported segment; it does not prove which record or operation caused it.
- In s730001 C repeat 5, the opening value was correct, but every reported checkpoint from record 400 onward was 60 too high. The first reported divergence is therefore in records 2-400, and the offset persists to the final answer. The record omission/arithmetic distinction remains unresolved.
- In s730002 E repeat 3, checkpoint errors were +155 at record 400, +210 at 800, then -25 at 1200 and 1600. The response supplied several incorrect intermediate totals despite stating the correct authority rule.

For R, a chronological prefix and a prefix of the updates that remain active at the end can legitimately differ. The CSV retains both. The response explicitly described checkpoints after resolving withdrawals, so the globally effective prefix is the relevant comparison; it would be incorrect to flag its first seven checkpoints using the chronological prefix instead.

The remaining eight failures do not expose enough intermediate computation to localize the mistake. No causal label is assigned from a numerical offset. In particular, legacy raw labels such as counted_gossip can appear for R even though its input contains no gossip; the neutral screen report correctly treats those as wrong_number.

## Targeted revision hypothesis

Keep the authority and reference-chain rules and the instruction to proceed directly when no conflict exists. Replace the vague checked-intermediate-results instruction with contiguous, nonoverlapping segments tied to source-record boundaries, carrying the preceding state once. Verify contributing records and operations, then explicitly reconcile the final segment. Do not require a printed table or prescribe the budget-specific backward/forward algorithms that underperformed in the draft screen.

This is a proposed improvement in verification, not a proven explanation or cure. Minimal v3 remains general in wording, contains no budget amounts, named Finance sources, seeds, or answers from this review, and will be evaluated on fresh seeds 740000-740004. The new pilot compares v3 with no skill; it does not directly estimate v3 minus v2.

## All minimal-v2 failures

| Trial | Expected | Answer | Difference |
| --- | ---: | ---: | ---: |
| [s730000_n1600_R_minimal_v2_gpt_r3](../attempts/s730000_n1600_R_minimal_v2_gpt_r3/20261026T004700Z_jeremyjcheng.json) | 1491 | 1314 | -177 |
| [s730000_n1600_E_minimal_v2_gpt_r3](../attempts/s730000_n1600_E_minimal_v2_gpt_r3/20261026T004730Z_jeremyjcheng.json) | 1491 | 1897 | +406 |
| [s730000_n1600_R_minimal_v2_gpt_r4](../attempts/s730000_n1600_R_minimal_v2_gpt_r4/20261026T005728Z_jeremyjcheng.json) | 1491 | 1486 | -5 |
| [s730000_n1600_R_minimal_v2_gpt_r5](../attempts/s730000_n1600_R_minimal_v2_gpt_r5/20261026T005902Z_jeremyjcheng.json) | 1491 | 1493 | +2 |
| [s730001_n1600_R_minimal_v2_gpt_r3](../attempts/s730001_n1600_R_minimal_v2_gpt_r3/20261026T010642Z_jeremyjcheng.json) | 1257 | 1347 | +90 |
| [s730001_n1600_R_minimal_v2_gpt_r2](../attempts/s730001_n1600_R_minimal_v2_gpt_r2/20261026T011008Z_jeremyjcheng.json) | 1257 | 1293 | +36 |
| [s730001_n1600_RG_minimal_v2_gpt_r2](../attempts/s730001_n1600_RG_minimal_v2_gpt_r2/20261026T011716Z_jeremyjcheng.json) | 1257 | 1221 | -36 |
| [s730001_n1600_E_minimal_v2_gpt_r4](../attempts/s730001_n1600_E_minimal_v2_gpt_r4/20261026T011726Z_jeremyjcheng.json) | 1257 | 1488 | +231 |
| [s730001_n1600_C_minimal_v2_gpt_r5](../attempts/s730001_n1600_C_minimal_v2_gpt_r5/20261026T011756Z_jeremyjcheng.json) | 1257 | 1317 | +60 |
| [s730001_n1600_RG_minimal_v2_gpt_r5](../attempts/s730001_n1600_RG_minimal_v2_gpt_r5/20261026T012255Z_jeremyjcheng.json) | 1257 | 1559 | +302 |
| [s730002_n1600_E_minimal_v2_gpt_r3](../attempts/s730002_n1600_E_minimal_v2_gpt_r3/20261026T012800Z_jeremyjcheng.json) | 2417 | 2392 | -25 |

Checkpoint calculations: [minimal_v2_checkpoint_audit.csv](minimal_v2_checkpoint_audit.csv).
