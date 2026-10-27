"""The prompt for one call: our system prompt, then the policy, the log, and the question as the user message."""

from __future__ import annotations

from dataclasses import dataclass

from experiment import text
from experiment.records import Record

SYSTEM = (
    "You will answer a question about records from a fictional organization. Use only the information supplied. "
    "You may work through the records before answering. End your response with one line in the form `ANSWER: $<number>K`."
)
# General candidate v1, injected verbatim in every skill arm. Development only: freeze
# the chosen wording and predictions before preparing a confirmatory main run.
SKILL = """Before answering from records that may contain conflicting information:

1. Establish which sources are authoritative for the question, using the rules provided. Do not assume that a newer statement or a more confident statement is automatically authoritative.
2. Identify relevant claims and the relationships between them, including corrections, replacements, withdrawals, and reinstatements. Distinguish an explicit revision from a statement that merely disagrees.
3. Resolve those relationships before combining information. A withdrawn instruction has no effect; withdrawing a withdrawal may restore the original information, according to the stated rules. Follow reference chains carefully.
4. Construct the current effective state from the information that remains valid. Keep superseded or withdrawn information separate from active information.
5. Check that the answer respects source authority, accounts for relevant revisions, and does not combine incompatible states.
6. If the rules or evidence leave a material conflict unresolved, state the uncertainty rather than inventing a resolution. Follow the requested answer format."""
# Text added after SYSTEM in each instruction arm.
INSTRUCTIONS = {"none": "", "skill": SKILL}


@dataclass(frozen=True)
class Prompt:
    system: str
    user: str


def system_prompt(instruction: str) -> str:
    if instruction not in INSTRUCTIONS:
        raise ValueError(f"unknown instruction {instruction!r}; defined: {', '.join(INSTRUCTIONS)}")
    extra = INSTRUCTIONS[instruction].strip()
    if instruction != "none" and not extra:
        raise ValueError(f"instruction {instruction!r} has no text yet; write it in experiment/prompts.py first")
    return f"{SYSTEM}\n\n{extra}" if extra else SYSTEM


def user_prompt(records: list[Record], project: str) -> str:
    return f"{text.render_log(records)}\n\nQuestion: {text.question(project)}"
