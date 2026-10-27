"""The prompt for one call: our system prompt, then the policy, the log, and the question as the user message."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from experiment import text
from experiment.records import Record

SYSTEM = (
    "You will answer a question about records from a fictional organization. Use only the information supplied. "
    "You may work through the records before answering. End your response with one line in the form `ANSWER: $<number>K`."
)
# Workflow V2, added after SYSTEM in the "skill" arm.
SKILL_FILE = Path(__file__).resolve().parent / "skills" / "workflow_v2.md"
SKILL = SKILL_FILE.read_text(encoding="utf-8").strip()
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
        raise ValueError(f"instruction {instruction!r} has no text yet; write it in {SKILL_FILE} first")
    return f"{SYSTEM}\n\n{extra}" if extra else SYSTEM


def user_prompt(records: list[Record], project: str) -> str:
    return f"{text.render_log(records)}\n\nQuestion: {text.question(project)}"
