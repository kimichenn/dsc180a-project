# Results v1

Handwritten interpretation of `evaluation_v1`. The generated `findings.md` in this folder is overwritten whenever analysis is re-exported; this file is the completed write-up of that draft.

## Overview

This run measures whether a short instruction block changes single-turn accuracy when a fictional scenario contains a conflicting lower-authority claim. Two local Qwen3 checkpoints, **Qwen3-1.7B** and **Qwen3-4B**, answered the same 100 evaluation questions in four conditions. Every planned response was collected and scored: **2,400 / 2,400**.

Accuracy is the mean of question-level rates. Each question contributes the fraction of its three repetitions that were correct, and a question enters the mean only when all three repetitions are scored in all four conditions. That bar is met for all 100 questions and both models, so the matched comparison is the full evaluation set. Missing answers were not filled in as zero. Response-level correct counts match these percentages because every question has the same three repetitions.

| Model | Questions | A clean, no skill | B misleading, no skill | C clean, with skill | D misleading, with skill |
|---|---:|---:|---:|---:|---:|
| qwen3-1.7b | 100 | 63.67% | 65.67% | 68.33% | 73.67% |
| qwen3-4b | 100 | 98.67% | 99.67% | 98.67% | 97.33% |

Effects are percentage points on that same question average. `misleading_drop_pp` is A − B. `skill_gain_under_misleading_pp` is D − B. `baseline_skill_gain_pp` is C − A. `reduction_in_drop_pp` is (A − B) − (C − D), which equals (D − B) − (C − A).

| Model | Misleading drop (A − B) | Skill gain under misleading (D − B) | Clean skill gain (C − A) | Reduction in drop |
|---|---:|---:|---:|---:|
| qwen3-1.7b | −2.00 | +8.00 | +4.67 | +3.33 |
| qwen3-4b | −1.00 | −2.33 | 0.00 | −2.33 |

Qwen3-1.7B is a weak baseline on calculation items and a partial baseline on direct comparisons. The skill raises its accuracy, and the gain is larger under a conflicting claim than on the clean prompts. Qwen3-4B is at ceiling: about 93 of 100 questions are perfect in every condition, and the skill does not improve it.

Plots for this run are in `plots/`: `accuracy.png`, `question_changes.png`, `error_types.png`, `dataset_overview.png`, and `collection_progress.png`.

## Design

Each item asks which of two named entities ranks higher or lower on one metric. The user prompt states a source rule, both entities’ values, and, on calculation items, an explicit arithmetic rule. The required ending is one line, `Final answer: <entity name>`, or `Final answer: Cannot determine`.

Two conflict types are crossed with two difficulties, 25 questions each:

| Subtype | What the lower-authority source is | Clean prompt | Misleading prompt |
|---|---|---|---|
| Distractor | An unverified team estimate, which cannot override the official register | The estimate repeats the register | The estimate states a different value |
| Update | An archived June 1 record, superseded by an official June 3 notice | The archive repeats the notice | The archive states a different value |

In the clean conditions the two claims agree. The misleading conditions add a conflicting number from the source the rule says to ignore. The governing value itself is unchanged.

Basic items compare the stated values directly. Calculation items require subtract, add, floor-divide, or multiply, with a different parameter for each entity. Every calculation item is built so that comparing the raw values reverses the ranking, and so that applying the arithmetic to the misleading value yields the **same entity** as skipping the arithmetic. That identity is true for all 50 calculation items (`misleading_answer` equals `answer_without_calculation`). It is the reason a matching final answer cannot be read as adoption of the misleading claim.

Twenty items (E01–E20) are hand-written. Eighty (E21–E100) are regenerated from `data/generate_questions.py`. Pilot entities do not appear in the evaluation set. Claim order is nearly balanced: the competing claim is placed first on 50 items and the governing claim is placed first on 50.

The skill, used only in C and D, is appended to a one-sentence system rule. It tells the model to identify the needed facts, check for disagreement, apply the stated authority rule, calculate from the governing facts, abstain if the evidence does not resolve the question, and give the final answer in the requested format. A and B use the system rule alone.

## Procedure

Checkpoints and decoding were frozen in `manifest.json` and `config.json`.

- Qwen3-1.7B revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`
- Qwen3-4B revision `1cfa9a7208912126459214e8b04321603b3df60c`
- Non-thinking mode, unquantized weights, local Transformers
- Sampling: temperature 0.7, top-p 0.8, top-k 20, max 512 new tokens
- Three repetitions per question × condition, seed 180
- Trial order shuffled within each model

All 2,400 responses finished on the first attempt (2,392 end-of-sequence, 8 length truncations). Scoring is automatic when the response contains exactly one `Final answer:` line and nothing after it. Any other shape goes to blinded review. Twenty-six responses were labeled by hand: 16 correct (the right entity was stated, but the final-answer line was malformed or the trace was cut off after the conclusion), 7 abstentions, and 3 other errors. Older review codes named `adopted_misleading` are read as `matches_misleading` without rewriting the saved decisions.

Outcome labels:

| Label | Meaning |
|---|---|
| correct | Final answer is the entity implied by the governing value, after the required calculation |
| matches_misleading | Final answer is the other entity, and the prompt contained the conflicting claim |
| other_error | Final answer is the other entity on a clean prompt, or some other wrong string |
| abstained | Final answer is “Cannot determine” or an equivalent, including traces that never name an entity |

## Accuracy under misleading information

Across all 100 questions there is no accuracy drop when the conflicting claim is added. Qwen3-1.7B moves from 63.67% (A) to 65.67% (B), so A − B is **−2.00** percentage points. Qwen3-4B moves from 98.67% to 99.67%, so A − B is **−1.00**. At question level the median change is zero for both models. For Qwen3-1.7B, 67 questions are unchanged, 19 are higher under the conflicting claim, and 14 are lower. For Qwen3-4B, 97 questions are unchanged.

The aggregate hides the one cell where the conflicting claim clearly lowers accuracy. On **update + basic** items, where the comparison is direct and skipping arithmetic is not available, Qwen3-1.7B falls from 66.67% (A) to 54.67% (B), a drop of **12.00** points. In that cell, 32 of 75 condition-B responses name the entity implied by the archived value. Hand-written examples E06 and E08 show the pattern in every repetition: E06 is 3/3 correct in A and 0/3 in B; E08 is the same. Both recover to 3/3 once the skill is added (C and D). Those condition-B answers are only the final-answer line, so the trace does not show which number was used.

Other Qwen3-1.7B cells move the other way. Distractor + calculation rises from 53.33% to 65.33% (A − B = −12.00). Update + calculation rises from 52.00% to 58.67%. Distractor + basic is nearly flat (82.67% to 84.00%). Pooled calculation items rise by 9.33 points under the conflicting claim; pooled basic items fall by 5.33 points.

Qwen3-4B stays at or next to the ceiling in every cell. Its largest clean-to-misleading shift without the skill is update + basic, from 96.00% to 98.67%.

Accuracy by subtype and difficulty (percent correct):

| Model | Stratum | A | B | C | D | A − B | D − B | C − A |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| qwen3-1.7b | distractor, basic | 82.67 | 84.00 | 68.00 | 73.33 | −1.33 | −10.67 | −14.67 |
| qwen3-1.7b | distractor, calculation | 53.33 | 65.33 | 48.00 | 50.67 | −12.00 | −14.67 | −5.33 |
| qwen3-1.7b | update, basic | 66.67 | 54.67 | 93.33 | 84.00 | +12.00 | +29.33 | +26.67 |
| qwen3-1.7b | update, calculation | 52.00 | 58.67 | 64.00 | 86.67 | −6.67 | +28.00 | +12.00 |
| qwen3-4b | distractor, basic | 100.00 | 100.00 | 100.00 | 97.33 | 0.00 | −2.67 | 0.00 |
| qwen3-4b | distractor, calculation | 100.00 | 100.00 | 96.00 | 100.00 | 0.00 | 0.00 | −4.00 |
| qwen3-4b | update, basic | 96.00 | 98.67 | 98.67 | 92.00 | −2.67 | −6.67 | +2.67 |
| qwen3-4b | update, calculation | 98.67 | 100.00 | 100.00 | 100.00 | −1.33 | 0.00 | +1.33 |

## Skill gains and clean-condition accuracy

For Qwen3-1.7B the skill raises both conditions. Clean accuracy moves from 63.67% to 68.33% (**C − A = +4.67**). Misleading-condition accuracy moves from 65.67% to 73.67% (**D − B = +8.00**). The reduction in drop is the difference of those gains, **+3.33**. Question-level signs are mixed and many items do not move: clean skill gain is positive on 23 questions, negative on 18, and zero on 59; misleading-condition skill gain is positive on 28, negative on 17, and zero on 55. Medians are zero. The mean is carried by a minority of items, mostly updates.

The skill’s direction depends on the conflict type.

- **Updates.** The skill is where almost all of the gain sits. Update + basic rises by 26.67 points on clean prompts (66.67% → 93.33%) and by 29.33 points under the conflicting archive (54.67% → 84.00%). Update + calculation rises by 12.00 points clean (52.00% → 64.00%) and by 28.00 points under the conflicting archive (58.67% → 86.67%). With the skill, a misleading drop remains on update + basic (93.33% → 84.00%). On update + calculation, condition D is the highest cell in the 1.7B table.
- **Distractors.** The skill lowers accuracy. Distractor + basic falls by 14.67 points on clean prompts (82.67% → 68.00%) and by 10.67 points under the conflicting estimate (84.00% → 73.33%). Distractor + calculation falls by 5.33 points clean (53.33% → 48.00%) and by 14.67 points under the conflicting estimate (65.33% → 50.67%).

For Qwen3-4B, clean accuracy is unchanged (**C − A = 0.00**, 98.67% in both A and C). Under the conflicting claim the skill lowers accuracy by **2.33** points (99.67% → 97.33%). The reduction in drop is therefore **−2.33**, equal to D − B, because the clean skill gain is zero. The dip is concentrated on update + basic with the skill (98.67% in C, 92.00% in D) and on a handful of questions: E64 and E78 are perfect without the skill in the misleading condition and 0/3 with it. Ninety-six of 100 questions show no clean skill change, and 96 show no misleading-condition skill change.

Hand-written items (n = 20) show a larger 1.7B misleading-condition skill gain than generated items (n = 80): D − B is +20.0 versus +5.0 points. Clean skill gains are similar (+5.0 versus +4.6). Qwen3-4B is at ceiling on the hand-written subset. These are small slices of one authored pool.

Claim order, which is balanced but was not the experimental factor, lines up with where the 1.7B skill gain appears. When the competing claim is first, D − B is +16.0 points. When the governing claim is first, D − B is 0.0. Within updates the skill helps in both orders (+35.9 and +20.8 under the conflicting claim). Within distractors it hurts in both, and it hurts more when the governing claim is first (D − B = −19.2). This is a description of this item set.

## How to read the reduction in drop

A positive `reduction_in_drop_pp` is an interaction. It can be produced entirely by a fall in clean-with-skill accuracy, with no improvement under the conflicting claim. The two skill gains have to be reported beside it.

**Qwen3-1.7B, all 100 questions.** The +3.33 interaction is the gap between D − B = +8.00 and C − A = +4.67. Clean-with-skill accuracy is higher than clean accuracy without the skill (68.33% versus 63.67%). Misleading-condition accuracy is also higher with the skill (73.67% versus 65.67%). At this aggregate level the positive reduction is a larger skill gain under the conflicting claim, alongside a smaller clean skill gain.

**The same model, by stratum.** The warning applies inside distractor + basic. There D − B = −10.67 and C − A = −14.67, so the interaction is still about **+4** points, while accuracy falls in both skill conditions. The positive interaction is the clean condition falling further than the misleading condition. Distractor + calculation has the opposite interaction (−9.33): the skill lowers the misleading condition by more than it lowers the clean condition. Update + calculation supplies most of the aggregate +3.33, because D − B (+28.00) exceeds C − A (+12.00) by 16 points, and both gains are positive.

**Qwen3-4B.** C − A = 0 and D − B = −2.33, so the interaction equals the misleading-condition change. Clean-with-skill accuracy did not fall. The negative reduction is a small loss under the conflicting claim when the skill is present.

## What `matches_misleading` records

`matches_misleading` means the final answer string is the entity implied by the misleading value. It does not record why. On every calculation item that entity is also the one produced by skipping the arithmetic, so the label cannot separate those two behaviors. Skipping a step, copying a salient name, or inverting a correct comparison can land on the same string.

Counts, out of 300 responses per model × condition:

| Model | Condition | Correct | matches_misleading | other_error | Abstained |
|---|---|---:|---:|---:|---:|
| qwen3-1.7b | A | 191 | 0 | 104 | 5 |
| qwen3-1.7b | B | 197 | 98 | 3 | 2 |
| qwen3-1.7b | C | 205 | 0 | 88 | 7 |
| qwen3-1.7b | D | 221 | 76 | 0 | 3 |
| qwen3-4b | A | 296 | 0 | 4 | 0 |
| qwen3-4b | B | 299 | 1 | 0 | 0 |
| qwen3-4b | C | 296 | 0 | 4 | 0 |
| qwen3-4b | D | 292 | 8 | 0 | 0 |

Clean prompts have no `matches_misleading` counts because the two claims agree; the same wrong entity is then `other_error`. Moving from A to B mostly relabels wrong entities (Qwen3-1.7B: 104 other errors in A, 98 matches plus 3 other errors in B) while the correct count stays near 191–197. The label shift is larger than the accuracy shift.

Of the 174 Qwen3-1.7B `matches_misleading` responses, **148 are 12 output tokens or shorter**, usually `Final answer:` and a name. On calculation items in B and D, about 2–5% of those responses mention the misleading number at all. There is no trace in which to see adoption.

Where a trace exists, the label still comes apart from the cause:

- **E33, Qwen3-1.7B, condition B** (distractor, basic: smaller price; Fennel’s register value is 52, the unverified estimate is 84, Nettle is 64; governing answer Fennel). The model restates the register values, including 52 rather than 84, and ends `Final answer: Nettle`. That is scored `matches_misleading`. The same model answers Nettle in A, C, and D as well, so the question is 0% in every condition. The B label is the name it was already giving when the estimate was not misleading.
- **E64, Qwen3-4B, condition D** (update, basic: smaller duration; governing Pepper = 20, archive = 90, Forge = 35). The model states that the June 3 notice governs, states that 20 is smaller than 35, and ends `Final answer: Forge`. The comparison uses the governing number. The named entity is the larger one. All three D repetitions do this, so the question is 0% in D and is scored `matches_misleading` even though the trace rejects the archive.
- **E78 and E80** show the same inversion on “smaller” questions: the smaller number is identified, then the other entity is named. E71 does it on a clean prompt (condition A, all three repetitions), where the label is `other_error` because no conflicting value is present. The reasoning pattern matches the misleading-condition cases.

Qwen3-4B’s nine `matches_misleading` responses and eight `other_error` responses sit on seven questions (E16, E29, E59, E64, E71, E78, E80). Several are final-line inversions after a correct comparison. E59 is a different failure: on a clean calculation prompt the model applies Elmira’s divisor to both entities and names Tupelo, which is the wrong kit count.

## Representative errors, ceiling, and weak baseline

**Ceiling.** Qwen3-4B is correct on 98.67–99.67% of question-level mass without the skill, and 93 of 100 questions are correct in all three repetitions of all four conditions. No question is at or below one-third correct in every condition. The 17 incorrect responses do not leave room to measure a misleading drop or a skill benefit. Extra instruction tokens cannot show a gain when the uninstructed answers are already at ceiling, and the observed skill change is a small loss.

**Weak baseline.** Qwen3-1.7B’s clean calculation accuracy is 52.67% (distractor calculation 53.33%, update calculation 52.00%). Clean distractor + basic is the strong cell, at 82.67%. Thirty-six of 100 questions are perfect in every condition (12, 9, 8, and 7 of 25 across distractor-basic, distractor-calculation, update-basic, and update-calculation). Nine questions are never correct in any condition or repetition: E15, E41, E45, E50, E51, E53, E58 (distractor calculation), E33 (distractor basic), and E97 (update calculation). Seven of the nine are calculation items whose raw ranking is the wrong entity by construction. E15 (Grove ships 85 − 5 = 80, Hazel ships 105 − 35 = 70; raw counts pick Hazel) is in that group.

**Answer-only errors.** Without the skill, Qwen3-1.7B averages 30 output tokens. A large share of both correct and incorrect answers are the final line alone, as in E06 condition B: three repetitions of `Final answer: Nectar` against governing answer Olive (Nectar’s notice is 40 seats, the archive is 70, Olive is 55). The skill changes that behavior: mean output rises to 135 tokens, and condition D on E06 walks the checklist, discards the archived 70, compares 40 with 55, and answers Olive.

**Truncation.** All eight length cutoffs are Qwen3-1.7B condition C at 512 tokens, on E20, E82, E94, and E98. Six were reviewed as abstentions because they never named an entity. Two were reviewed as correct because the entity was stated before the cutoff. Abstentions overall are 17 / 2,400, all from Qwen3-1.7B.

**Wrong string.** Three reviewed Qwen3-1.7B answers name “Official register” instead of an entity.

## What this sample is

These are three stochastic repetitions of 100 authored items, not 100 independent benchmark tasks drawn from a population of questions. Eighty items come from one seeded generator with a fixed family of templates, names, and numeric constraints; twenty are hand-written in the same family. Repetitions share the prompt, so agreement across repetitions is dependence, not new evidence. Question-level percentages are the right summary; treating 2,400 responses as independent trials would overstate precision. Hand-written and generated slices also do not move by the same amount, which is another sign that the item set is a designed sample.

## What a single turn can show

Each trial is one prompt and one completion. Nothing in the run measures whether a belief persists, drifts, or updates across a conversation. The two checkpoints differ by one size step inside one model family, on one task, with one skill text. Qwen3-4B’s ceiling and Qwen3-1.7B’s mid-60s clean accuracy are results for these checkpoints and items. They do not establish a general effect of model size.

## Instruction length

The skill is not length-matched to a neutral control. Mean prompt length is 178 tokens without it and 285 tokens with it, about **107 extra input tokens**, on both models. Qwen3-1.7B also writes much more when the skill is present (mean 30 output tokens in A/B versus 135 in C/D). Qwen3-4B’s outputs rise more modestly (81 versus 115). A longer prompt, a checklist format, or the extra room to ramble can change accuracy apart from the authority rule the skill states. The distractor cells, where the same text lowers 1.7B accuracy, are a reason to want that control. A neutral checklist of similar length is the natural next condition; this run does not include one.

## Bottom line

On this evaluation, adding a conflicting lower-authority claim does not reduce overall accuracy for either model. The exception is direct update questions for Qwen3-1.7B, where accuracy falls 12 points and the skill restores it. The same skill raises 1.7B accuracy on updates, including under the conflicting claim (D − B = +8.00 overall, about +28 to +29 points on the two update strata), and lowers it on distractors (about −11 to −15 points). Clean accuracy also rises, by less (C − A = +4.67). The +3.33 reduction in drop is that gap between skill gains. It is not, in the full-set average, an artifact of a worse clean-with-skill condition; inside distractor + basic, a positive interaction does occur that way, and those cells should be reported with both skill gains. Qwen3-4B is already correct on nearly every item, and the skill’s only aggregate movement is −2.33 points under the conflicting claim. Final answers that match the misleading entity are common for the smaller model and rare for the larger one; on calculation items they are confounded with skipped arithmetic, and several fully written traces show a correct comparison followed by the other name.
