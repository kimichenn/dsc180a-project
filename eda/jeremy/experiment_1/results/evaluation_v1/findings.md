# EDA findings

Collected responses: 2400/2400.
Scored responses: 2400/2400.

All planned responses scored.

Accuracy uses only questions with every repetition scored in all four conditions.

            questions      A      B      C      D
model                                            
qwen3-1.7b        100  63.67  65.67  68.33  73.67
qwen3-4b          100  98.67  99.67  98.67  97.33

Effects in percentage points:
            misleading_drop_pp  skill_gain_under_misleading_pp  baseline_skill_gain_pp  reduction_in_drop_pp
model                                                                                                       
qwen3-1.7b                -2.0                            8.00                    4.67                  3.33
qwen3-4b                  -1.0                           -2.33                    0.00                 -2.33

## Interpretation to complete

- Describe any accuracy drop under misleading information.
- Describe skill gains and any change in clean-condition accuracy.
- A positive reduction_in_drop_pp can result from lower clean-with-skill accuracy alone; report D-B (skill_gain_under_misleading_pp) alongside C-A (baseline_skill_gain_pp).
- matches_misleading records only a final-answer match to the misleading answer, not its cause. Skipping arithmetic can produce the same answer; this label does not establish adoption of misinformation.
- Include representative errors and report ceiling or weak-baseline results.
- These are repeated measurements of a small authored set, not independent benchmark items.
- This single-turn study does not measure drift or establish a general model-size effect.
- Extra instructions are not length-matched; a neutral checklist is a future control.
