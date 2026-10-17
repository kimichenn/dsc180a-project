"""Turn a scenario plus a condition into the exact system prompt and messages a model sees.

Context layout (top to bottom), shared by both delivery formats:

    [source rule]          rule placement = "start"
    background             inference rule + supporting fact
    lead filler            keeps a start-placed rule far from the claims
    [source rule]          rule placement = "near"
    claim segment          claims in date order; "far" puts the mid filler between the
                           governing claim and the non-governing claim(s)
    question

Multi-document prompts may reverse the claim segment (counterbalancing); dates stay fixed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from conflict_eval.scenarios import FillerPassage, Scenario
from harness.prompts import Prompt

COMMON_INSTRUCTION = (
    "You will answer a question about a fictional scenario. "
    "Use only the information supplied in the scenario. Answer briefly."
)
WARNING = "The provided context may contain conflicting information. Answer carefully."
SKILL = """When answering from provided context:

1. Identify the claims relevant to the question.
2. Check whether any relevant claims disagree.
3. If they disagree, apply the source-authority and update rules stated in the context to determine which claim governs.
4. If an authoritative source explicitly supersedes an earlier value, use the updated value.
5. If the provided rules do not resolve the conflict, say that it cannot be resolved.
6. Give a definite answer when the available evidence does resolve it."""
INSTRUCTIONS = {"none": None, "warning": WARNING, "skill": SKILL}
ACKNOWLEDGEMENT = "Understood."

VARIANTS = ("consistent", "conflict")
DISTANCES = ("near", "far")
RULE_PLACEMENTS = ("start", "near")
INSTRUCTION_LEVELS = tuple(INSTRUCTIONS)
DOC_ORDERS = ("forward", "reversed")
MAX_RUNG = 4


@dataclass(frozen=True)
class Condition:
    variant: str
    question_type: str
    distance: str
    rule_placement: str
    instruction: str
    rung: int = 0
    doc_order: str = "forward"


@dataclass(frozen=True)
class Block:
    kind: str  # rule | background | filler | claim
    body: str
    source: str = ""
    date: date | None = None
    role: str = ""  # claims only: governing | competing | extra. Never rendered.



def system_prompt(instruction: str) -> str:
    extra = INSTRUCTIONS[instruction]
    return COMMON_INSTRUCTION if extra is None else f"{COMMON_INSTRUCTION}\n\n{extra}"


def build_blocks(scenario: Scenario, condition: Condition, filler: list[FillerPassage]) -> list[Block]:
    per_block = 2 if condition.rung >= 1 else 1  # rung 1 doubles every filler block
    if len(filler) < 2 * per_block:
        raise ValueError(f"rung {condition.rung} needs {2 * per_block} filler passages, found {len(filler)}")
    lead, mid = filler[:per_block], filler[per_block : 2 * per_block]

    rule = Block("rule", scenario.source_rule)
    background = Block(
        "background",
        f"{scenario.inference_rule}\n{scenario.supporting_source}: {scenario.supporting_text}",
    )
    blocks = [rule] if condition.rule_placement == "start" else []
    blocks.append(background)
    blocks += [_filler_block(p) for p in lead]
    if condition.rule_placement == "near":
        blocks.append(rule)
    blocks += _claim_segment(scenario, condition, mid)
    return blocks


def build_prompt(scenario: Scenario, condition: Condition, filler: list[FillerPassage]) -> Prompt:
    if scenario.format == "multi_turn" and condition.doc_order != "forward":
        raise ValueError("multi-turn context is always chronological")
    blocks = build_blocks(scenario, condition, filler)
    question = f"Question: {scenario.questions[condition.question_type]}"

    if scenario.format == "multi_document":
        documents = "\n\n".join(f"Document {i}\n{render_block(b)}" for i, b in enumerate(blocks, 1))
        messages = [{"role": "user", "content": f"{documents}\n\n{question}"}]
    else:
        messages = []
        for block in blocks:
            messages.append({"role": "user", "content": render_block(block)})
            messages.append({"role": "assistant", "content": ACKNOWLEDGEMENT})
        messages.append({"role": "user", "content": question})
    return Prompt(system_prompt(condition.instruction), messages)


def render_block(block: Block) -> str:
    if not block.source:
        return block.body
    label = block.source if block.date is None else f"{block.source}, {block.date:%B} {block.date.day}"
    return f"Source: {label}\n{block.body}"


def _filler_block(passage: FillerPassage) -> Block:
    return Block("filler", passage.text, source=passage.source)


def _claim_blocks(scenario: Scenario, condition: Condition) -> list[Block]:
    """Claims in date order, carrying the values and wording this condition calls for."""
    conflict = condition.variant == "conflict"
    # Consistent variant: the later claim repeats the earlier claim's value.
    governing_value = scenario.governing.value if conflict else scenario.earlier_value
    competing_value = scenario.competing.value if conflict else scenario.earlier_value

    claims = [("governing", scenario.governing, governing_value), ("competing", scenario.competing, competing_value)]
    if condition.rung >= 4:
        claims.append(("extra", scenario.extra_competing, competing_value))
    claims.sort(key=lambda c: c[1].date)

    blocks = []
    for role, claim, value in claims:
        text = claim.render(value)
        if condition.rung >= 2 and role == scenario.later_role:
            text = scenario.paraphrase.conflict if conflict else scenario.paraphrase.consistent
        if condition.rung >= 3 and role == "competing":
            text = f"{text} {scenario.confidence_cue}"
        blocks.append(Block("claim", text, source=claim.source, date=claim.date, role=role))
    return blocks


def _claim_segment(scenario: Scenario, condition: Condition, mid_filler: list[FillerPassage]) -> list[Block]:
    segment = _claim_blocks(scenario, condition)
    if condition.distance == "far":
        # Validation guarantees the governing claim is first or last in date order.
        governing_at = next(i for i, b in enumerate(segment) if b.role == "governing")
        cut = 1 if governing_at == 0 else governing_at
        segment[cut:cut] = [_filler_block(p) for p in mid_filler]
    if condition.doc_order == "reversed":
        segment.reverse()
    return segment
