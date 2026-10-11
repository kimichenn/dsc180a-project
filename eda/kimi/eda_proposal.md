# LLM Robustness to Conflicting Information

## Part 1: Proposal

### Research question

**When an LLM's context contains two conflicting claims and enough provenance to tell which one governs, how often does the other claim contaminate its answers, and can a reusable conflict-resolution skill reduce that?**

This phase is exploratory. The goal is to find where frontier models (GPT, Claude, Gemini) start to fail and whether the skill looks promising enough to study formally in DSC 180B. It is not a benchmark and makes no claim about which model is best.

### Construct

Each scenario contains two incompatible claims about a made-up operational fact (a launch date, a sensor reading, an inventory count). Made-up facts mean the answer can only come from the context. Every scenario includes a rule that makes one claim govern.

| Conflict subtype             | Example                                                               | Governing claim |
| ---------------------------- | --------------------------------------------------------------------- | --------------- |
| Non-authoritative distractor | Database says October 18; unverified team notes say October 28        | October 18      |
| Superseding update           | Database says October 18; a later official correction says October 28 | October 28      |

The two subtypes defeat opposite shortcuts: "trust the earlier claim" fails on updates, and "trust the later claim" fails on distractors.

Each conflict scenario has a matched **Consistent** version with the same sources, structure, and length, where the second source agrees with or confirms the first.

### Conditions

|                | No extra instruction | One-line warning   | Full skill       |
| -------------- | -------------------- | ------------------ | ---------------- |
| **Consistent** | Baseline             | Warning control    | Skill control    |
| **Conflict**   | Conflict             | Conflict + warning | Conflict + skill |

### Difficulty variables

| Variable       | Levels                                                                                                                                                  |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Question type  | Direct: "When does Vela launch?" / One-step: "Which project launches first, Vela or Orion?" / Two-step: "Which project enters QA first, Vela or Orion?" |
| Distance       | Claims adjacent / claims separated by a fixed filler block                                                                                              |
| Rule placement | Authority rule next to the claims / rule stated once at the start, far from the claims                                                                  |

Two-step questions need the resolved fact to pass through a stated inference rule before the comparison ("Projects enter QA 4 days before launch"). The matched Consistent version shows whether a failure comes from the conflict or from the reasoning alone.

### Measures

Each response gets one label: **Correct**, **Adopted non-governing claim**, **No committed answer**, or **Other error**. A separate yes/no flag records whether the model mentioned the conflict.

- **Accuracy:** scenarios correct out of the total, per condition.
- **Adoption rate:** share of conflict responses that used the non-governing claim.
- **Conflict drop:** Conflict accuracy minus Consistent accuracy, per scenario.
- **Skill recovery:** Conflict + skill accuracy minus Conflict accuracy, per scenario.

A response that notes the conflict and gives the governing answer counts as Correct.

### Working hypotheses

- **H1:** Conflict lowers accuracy against the matched Consistent version, and the drop grows from direct to one-step to two-step questions.
- **H2:** The full skill raises Conflict accuracy above both no instruction and the one-line warning.
- **H3:** The skill does not lower accuracy or add hedging in the Consistent condition.
- **H4:** Models fail differently on the two subtypes (for example, handling updates well but falling for later distractors).

### Plan in brief

| Stage            | Purpose                                                               | Scenarios | Responses     |
| ---------------- | --------------------------------------------------------------------- | --------- | ------------- |
| 0. Ceiling probe | Check that failures exist at the hardest setting before building more | 8         | 144 per round |
| 1. Failure map   | See which difficulty variables matter                                 | 12        | 432           |
| 2. Skill test    | Fill the six-condition table at one chosen setting                    | 12        | 432           |

### What this does and does not show

- It measures a model's ability to resolve **synthetic conflicts with an explicit resolution rule**. It is not a general measure of resistance to misinformation.
- The skill restates the kind of rule the scenarios are built on (source authority plus official supersession). A gain shows that prompting the procedure helps on rule-shaped items, not that the skill generalizes.
- Stage 2 reuses the Stage 1 scenarios, so the skill result is exploratory. A held-out set belongs in 180B.
- If the study only finds failures after adding bias cues (ladder rungs 3 and 4), the finding is about susceptibility to confidence or repetition, and is reported that way.

---

## Part 2: Protocol

### Stage 0: ceiling probe

Run this before writing more than 8 scenarios.

- **Scenarios:** 8 (4 distractor, 4 update; half multi-turn, half multi-document).
- **Setting:** two-step question, far distance, rule stated once at the start, no extra instruction.
- **Runs:** Consistent and Conflict, 3 models, 3 generations each: 8 x 2 x 3 x 3 = 144 responses.
- **Scenario result:** the majority outcome of the 3 generations. Read all three whenever they disagree.

**Decision rule:**

1. Go to Stage 1 if at least one model gets at least 7 of 8 Consistent scenarios correct and at least 2 of the 8 matched Conflict scenarios wrong.
2. Otherwise climb one rung on the ladder below and rerun the probe.
3. If every rung is exhausted with no qualifying model, report the ceiling result.

The rung reached in Stage 0 is frozen for Stages 1 and 2.

**Difficulty ladder** (add one rung at a time, keep earlier rungs):

| Rung | Change                                                                         | Type                   |
| ---- | ------------------------------------------------------------------------------ | ---------------------- |
| 1    | Double the filler block                                                        | Same construct, harder |
| 2    | Paraphrased contradiction ("pushed back ten days" in place of a restated date) | Same construct, harder |
| 3    | Confident wording on the non-governing claim ("confirmed with the whole team") | Adds a persuasion cue  |
| 4    | Two non-governing sources that agree                                           | Adds a repetition cue  |

Rungs 1 and 2 make the same task harder. Rungs 3 and 4 introduce new influences, so they come last and are labeled as such in any result.

**Smaller models:** adding one is a diagnostic extension after a ceiling result. It does not count as evidence for the frontier-model question.

### Stage 1: failure map

- **Scenarios:** 12 (the 8 from the probe plus 4 more, same balance), at the frozen rung.
- **Design:** Consistent vs. Conflict, three question types, near vs. far, no extra instruction.
- **Runs:** 12 x 2 x 3 x 2 x 3 models x 1 generation = 432 responses.
- **Output:** correct counts and adoption rate by question type, distance, subtype, format, and model, plus a read-through of the failures.

**Rule for choosing the Stage 2 setting** (fixed in advance; one setting for all models):

1. Keep settings where every model gets at least 11 of 12 Consistent scenarios correct.
2. Of those, keep settings where at least two of the three models get between 6 and 10 of 12 Conflict scenarios correct.
3. Pick the one whose median model is closest to 8 of 12.
4. If no setting passes step 2, use the setting with the most Conflict errors and say so in the write-up.

### Stage 2: skill test

- **Design:** Consistent vs. Conflict, three instruction levels, at the chosen setting.
- **Runs:** 12 x 2 x 3 x 3 models x 2 generations = 432 responses.
- **Output:** the six-condition table per model, with per-scenario conflict drop and skill recovery. All three models are shown separately.

### Prompts

**Common instruction (all conditions):**

> You will answer a question about a fictional scenario. Use only the information supplied in the scenario. Answer briefly.

**One-line warning:**

> The provided context may contain conflicting information. Answer carefully.

**Full skill** (frozen before Stage 0):

> When answering from provided context:
>
> 1. Identify the claims relevant to the question.
> 2. Check whether any relevant claims disagree.
> 3. If they disagree, apply the source-authority and update rules stated in the context to determine which claim governs.
> 4. If an authoritative source explicitly supersedes an earlier value, use the updated value.
> 5. If the provided rules do not resolve the conflict, say that it cannot be resolved.
> 6. Give a definite answer when the available evidence does resolve it.

The skill does not name position, repetition, or confidence. If it still holds up on rungs 3 and 4, that result is not explained by the skill listing the exact cue being tested.

The warning or skill is appended to the common instruction. Scenario facts are always user-side content.

### Delivery formats

- **Multi-document:** labeled documents in one prompt. Document order is counterbalanced; timestamps stay fixed.
- **Multi-turn:** context spread across user turns in chronological order, with fixed "Understood." assistant turns between them so the model never commits to a claim before the question.

Presentation order and event time are not fully separable in the multi-turn format, so position effects are treated as exploratory.

### Scenario rules

- **Every inference rule is stated in the context.** The scenario says "Projects enter QA 4 days before launch"; the question never relies on an unstated link such as launch date implying resource timing.
- **Questions never restate the claims.**
- **The answer must flip** depending on which claim is used, for both one-step and two-step questions.
- **Balance surface patterns:** the governing value is not always the earlier date, the smaller number, or the first-named entity.
- **Vary domains:** project management, equipment monitoring, logistics, inventory, scheduling.
- **Filler** is identical across matched variants, has a recorded token length, and contains nothing relevant to the target entities, the governing rule, the disputed attribute, or the answer. Other names, dates, and numbers are allowed; the first round uses plain filler without them.

**Validation checklist** (by hand, before any model run):

1. The rule makes the governing claim unambiguous.
2. Each of the three questions has exactly one intended answer.
3. Swapping to the non-governing claim flips the one-step and two-step answers.
4. Consistent and Conflict versions differ only in the second claim's value.

A Consistent-condition error triggers a manual review of the item. Revise or drop it only if the scenario itself is ambiguous.

### Scenario record

```json
{
    "id": "vela-01",
    "domain": "project_management",
    "format": "multi_turn",
    "conflict_subtype": "non_authoritative_distractor",
    "source_rule": "The project database is the source of record. Team notes are unverified.",
    "governing_claim": { "source": "Project database", "value": "October 18" },
    "competing_claim": { "source": "Team notes", "value": "October 28" },
    "supporting_fact": {
        "source": "Project database",
        "text": "Project Orion launches October 24."
    },
    "inference_rule": "Projects enter QA 4 days before launch.",
    "q_direct": "When does Project Vela launch?",
    "answers_direct": { "correct": "October 18", "nongoverning": "October 28" },
    "q_one_step": "Which project launches first, Vela or Orion?",
    "answers_one_step": { "correct": "Vela", "nongoverning": "Orion" },
    "q_two_step": "Which project enters QA first, Vela or Orion?",
    "answers_two_step": { "correct": "Vela", "nongoverning": "Orion" }
}
```

Check on the two-step item: Orion enters QA October 20. Vela enters QA October 14 under the governing claim and October 24 under the competing one, so the answer flips.

The governing/competing labels are used only by the harness and scorer and never appear in the prompt.

### Scoring

- Answers are short and closed-form (a date, a name, a value, one of two options).
- Normalize and string-match first; hand-label anything that does not match, using the four labels above.
- Keep every raw response.

### Run controls

- Choose one flagship model per provider before Stage 0 and record its exact identifier, the run date, sampling settings, and reasoning setting.
- Keep the reasoning setting fixed per model. Comparing standard and extended reasoning is a separate experiment.
- Disable tools, browsing, retrieval, and memory. Start every trial in a fresh context.
- Interleave conditions in random order.
- Repeated generations of one scenario are not independent items; collapse them to one scenario result before comparing conditions.

### Deferred to 180B

- A frozen held-out scenario set for the skill evaluation
- Blinded, double-coded manual scoring
- A length-matched generic checklist as an extra control for the skill
- A skill variant that names specific cues (position, repetition, confidence), compared against the general one
- Bootstrap intervals and mixed-effects models
- Independent manipulation of presentation order and event time
- Realistic filler containing unrelated names, dates, and numbers
