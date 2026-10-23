"""The prompt for one call: our system prompt, then the policy, the log, and the question as the user message."""

from __future__ import annotations

from dataclasses import dataclass

from experiment import text
from experiment.records import Record

SYSTEM = (
    "You will answer a question about records from a fictional organization. Use only the information supplied. "
    "You may work through the records before answering. End your response with one line in the form `ANSWER: $<number>K`."
)
# Text added after SYSTEM for each instruction arm. Only the no-skill arm exists so far; the
# conflict-resolution skill (and a neutral text of the same length) go here once their wording is frozen.
INSTRUCTIONS: dict[str, str | None] = {"none": None}


@dataclass(frozen=True)
class Prompt:
    system: str
    user: str


def system_prompt(instruction: str) -> str:
    if instruction not in INSTRUCTIONS:
        raise ValueError(f"unknown instruction {instruction!r}; defined: {', '.join(INSTRUCTIONS)}")
    extra = INSTRUCTIONS[instruction]
    return SYSTEM if extra is None else f"{SYSTEM}\n\n{extra}"


def user_prompt(records: list[Record], project: str) -> str:
    return f"{text.render_log(records)}\n\nQuestion: {text.question(project)}"
