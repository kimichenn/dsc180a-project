"""Instructions from the v4 protocol. The log and question are always user-side content."""

from __future__ import annotations

from conflict_eval.prompts import Prompt

_ANSWER_FORMAT = "`ANSWER: ` followed by the project names separated by commas, or `ANSWER: none`."
COMMON_INSTRUCTION = (
    "You will answer a question about records from a fictional organization. Use only the information supplied. "
    f"You may work through the records before answering. End your response with one line in the form {_ANSWER_FORMAT}"
)
# Stage A rule 3: a final-answer-only format, applied to every condition when used.
FINAL_ONLY_INSTRUCTION = (
    "You will answer a question about records from a fictional organization. Use only the information supplied. "
    f"Respond with only one line in the form {_ANSWER_FORMAT}"
)
WARNING = "The provided context may contain conflicting information. Answer carefully."
SKILL = """When answering from provided context:

1. Identify the claims relevant to the question.
2. Check whether any relevant claims disagree.
3. If they disagree, apply the source-authority and update rules stated in the context to determine which claim governs.
4. If an authoritative source explicitly supersedes an earlier value, use the updated value.
5. When the answer depends on many items, determine the governing value for each item before combining them.
6. If the provided rules do not resolve the conflict, say that it cannot be resolved.
7. Give a definite answer when the available evidence does resolve it."""
INSTRUCTIONS = {"none": None, "warning": WARNING, "skill": SKILL}
RESPONSE_FORMATS = ("working", "final_only")


def system_prompt(instruction: str, response_format: str = "working") -> str:
    base = FINAL_ONLY_INSTRUCTION if response_format == "final_only" else COMMON_INSTRUCTION
    extra = INSTRUCTIONS[instruction]
    return base if extra is None else f"{base}\n\n{extra}"


def build_prompt(log_text: str, question: str, instruction: str, response_format: str = "working") -> Prompt:
    user = f"{log_text}\n\nQuestion: {question}"
    return Prompt(system_prompt(instruction, response_format), [{"role": "user", "content": user}])
