"""Parse the final ANSWER line into $K and give each response one category."""

from __future__ import annotations

import re

from chain.resolver import LURES
from harness.answers import ANSWER_LINE

# "810", "$810K", "810K", "$810,000", "810 thousand", "$1.2M"
_NUMBER = re.compile(r"\$?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|m|million)?\b", re.IGNORECASE)
CATEGORIES = ("correct", *LURES, "missed_one_update", "other", "format_failure", "truncated")


def parse_answer(response: str | None) -> int | float | None:
    """The budget in $K from the last ANSWER line, or None when there is no answer line or number."""
    text = response or ""
    matches = list(ANSWER_LINE.finditer(text))
    if not matches:
        return None
    body = matches[-1].group(1)
    if not _NUMBER.search(body):  # "ANSWER:" with the number on the next line
        following = text[matches[-1].end() :].strip().splitlines()
        body = following[0] if following else ""
    number = _NUMBER.search(body)
    if not number:
        return None
    value = float(number[1].replace(",", ""))
    unit = (number[2] or "").lower()
    if unit in ("m", "million"):
        value *= 1000
    elif not unit and value >= 100_000:  # written in dollars, e.g. $810,000
        value /= 1000
    return int(value) if value == int(value) else value


def is_truncated(finish_reason: str | None) -> bool:
    """Output cut off at the token limit (OpenAI incomplete:max_output_tokens, Claude max_tokens, Gemini MAX_TOKENS)."""
    reason = (finish_reason or "").lower()
    return "max_output_tokens" in reason or reason == "max_tokens"


def score_response(response: str | None, finish_reason: str | None, meta: dict, version: str) -> dict:
    """Correct, else the first matching wrong strategy. Format failures and truncations stay separate from 'other'."""
    value = parse_answer(response)
    truncated = is_truncated(finish_reason)
    answer = meta["answer"]
    if value is None:
        category = "truncated" if truncated else "format_failure"
    elif value == answer:
        category = "correct"
    else:
        lures = meta["lures"][version]
        category = next((name for name in LURES if lures.get(name) == value), None)
        if category is None:
            changes = {abs(r["amount"]) for r in meta["records"]
                       if r["entity"] == meta["project"] and r["op"] == "adjust" and r["active"]}
            category = "missed_one_update" if abs(value - answer) in changes else "other"
    return {
        "value": value,
        "correct": category == "correct",
        "category": category,
        "format_failure": value is None,
        "truncated": truncated,
    }
