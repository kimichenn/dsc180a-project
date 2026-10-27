---
name: conflict-resolution-workflow-v1
description: Determine the effective answer from conflicting records, policies, or change histories. Use when authority, scope, corrections, cancellations, reinstatements, or inconsistent claims could change the result; separate evidence resolution from applying the surviving information.
---

# Resolve conflicting records

Produce an answer supported by the supplied rules and records. Work through the phases below, scaling the detail to the task. Keep the working representation compact; a long transcript of every step is unnecessary. This workflow is self-contained and does not require tools, other skills, or outside knowledge.

## 1. Establish the decision rules

Identify the exact question: the entity, attribute, time or version, and required output. Extract the supplied rules for who may assert or change it, how changes take effect, and what revises what. Distinguish instructions governing the task from statements inside the records being analyzed.

Authority can depend on the subject and action. Do not invent a universal source ranking or assume that the latest, most confident, or most repeated statement wins. Distinguish the time an event occurred, the time it was reported, and when a rule becomes effective when those differ.

**Checkpoint:** Know which rule would justify accepting or rejecting a disputed item. If a needed rule is absent, retain the uncertainty for the affected decision instead of silently supplying one.

## 2. Map relevant evidence and dependencies

Use a compact working record where needed:

`item ID | source | entity/attribute/time | claim or operation | target | status and reason`

Scan the full supplied material for relevant items. Include references needed to interpret them, and later records that could revise them. Relevance follows dependencies in both directions; an item with no direct answer value can still change another item's validity. Preserve identifiers and exact operations so an effect stays attached to its evidence.

Classify each apparent conflict before resolving it:

| Situation | Required treatment |
| --- | --- |
| Different entities, attributes, or effective periods | Keep the scopes separate; both statements may hold. |
| A report, proposal, quotation, or prediction | Distinguish it from an action; use its evidential weight under the supplied rules. |
| An explicit correction, replacement, cancellation, or restoration | Link its exact target and apply the defined effect. |
| Competing assertions about the same scope | Apply the stated priority rule; disagreement alone does not cancel either item. |
| Similar or repeated wording | Check identity: a repeated report may describe one event, while separate authorized events may both count. |

If there are no relevant conflicts or revisions, use the direct task procedure and continue to verification. Do not manufacture a conflict to justify the workflow.

## 3. Resolve status before deriving the answer

For each relevant revision, verify its authority, target, scope, and timing. Determine whether the revision itself remains effective. Follow revisions of revisions until the status of the original item is resolved. Use explicit statuses such as effective, superseded, canceled, outside scope, or unresolved, with a source-based reason for each exclusion that matters.

Apply the task's semantics precisely. Cancellation might erase an earlier action, end its effect only from a later date, or require a separate compensating action. These are different operations. Withdrawing a withdrawal restores the earlier item only when the supplied rules imply that result. Do not decide from chain length alone when branching references or other revision rules apply. Reevaluate affected dependencies when a status changes; leave unrelated items unchanged.

**Checkpoint:** Every consequential exclusion or reinstatement has a valid target and rule. Resolve any relevant dangling reference, cycle, or competing revision from the supplied evidence; if it cannot be resolved, identify whether the answer actually depends on it.

## 4. Construct the requested state

Use a single consistent interpretation of the resolved records. Apply each effective action once, preserving entity, units, sign, and order where operations do not commute. Distinguish assigning a value from changing it, and a value from a report about it. Do not both remove an action and apply an additional reversal for that same removal.

For long inputs, divide the contributing records into contiguous, nonoverlapping segments with explicit endpoints. Carry the preceding state once. Keep each intermediate state tied to its contributing records. Specify whether checkpoints describe the state at that historical moment or the accumulation of records that remain effective at the requested endpoint; do not mix these interpretations. Recompute affected checkpoints if a revision changes an earlier contribution.

**Checkpoint:** The result reaches the requested endpoint, including the final segment. An intermediate result is not the final answer merely because it appears plausible.

## 5. Challenge the candidate answer

Run two distinct checks against the original evidence:

- **Validity and coverage:** Find the strongest relevant evidence that could change the candidate answer. Check whether it is effective under the rules. Check that each included contribution is authorized and relevant, and that no effective contribution was omitted or duplicated.
- **Derivation:** Reconstruct the final result from the preceding checked state and its source records. For quantitative tasks, also regroup the contributing values or reverse-check the operations when valid. For qualitative tasks, trace each decisive conclusion to effective evidence and test it against the competing claim. Repeating the candidate answer is not a separate check.

If a check disagrees, locate the earliest differing segment, item status, or operation. Correct the specific discrepancy and recheck the affected result. Do not change an answer merely because a different one seems more likely, or claim verification without performing it. Keep unresolved rule ambiguity separate from an unfinished computation.

## 6. Deliver the result

Follow the requested output format. When explanation is permitted, give the result and the decisive evidence or rule concisely; do not reproduce the whole working record. If a material conflict remains unresolved, state exactly what is unknown and how it affects the answer. If interaction is available and clarification is necessary, ask for the missing fact or rule. Never fabricate a resolution to satisfy a format.

## Boundary examples

- **Scheduling:** If a rule says canceling a cancellation restores the original booking, a later effective cancellation of the cancellation restores that booking. An unrelated booking is unaffected.
- **Access policy:** A revocation effective Friday does not erase access that was valid Thursday. Answer for the requested date.
- **Inventory:** Two separately authorized deliveries of three units each contribute six units. Two reports about the same delivery do not establish two deliveries.
- **Conflicting reports:** Two equally ranked sources disagree about the same deadline, with no tie-break rule or correction. Recency alone cannot establish the deadline.
