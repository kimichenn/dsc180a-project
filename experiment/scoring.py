"""Read the number from a response and put the answer in exactly one bucket.

Buckets, in the order they are assigned (d = answer - correct budget):
    correct                  d = 0
    cut_off                  hit the output limit with no ANSWER line
    gave_up                  refused, abstained, or otherwise no ANSWER line with a number
    ignored_all_withdrawals  equals the opening budget plus every Finance change, withdrawn or not
    missed_withdrawal        d = +amount of one withdrawn change
    dropped_reinstated       d = -amount of one change a withdrawal of a withdrawal restored
    counted_gossip           d = the change one relative gossip claim states
    off_by_one_regular       |d| = the amount of one change no withdrawal touches
    other                    anything else, such as several mistakes at once
A response that hit the output limit is still scored on its final ANSWER line when it has one;
hit_length_limit flags it, by the same rule for every model.

Each bucket's values come from the records' roles in the full log, so a mistake on a record lands in
the same bucket in every version: dropping a change that R reinstates is dropped_reinstated in C and
E too. That makes C and E baselines for how often each bucket turns up without withdrawals. The
values come from solvers.flipped, so a mishandled nested withdrawal lands in its bucket straight
from the solver, and the generator resamples any log where two buckets share a value or one equals
the answer.
"""

from __future__ import annotations

import re

from experiment import solvers
from experiment.records import Record

BUCKETS = (
    "correct", "cut_off", "gave_up", "ignored_all_withdrawals", "missed_withdrawal",
    "dropped_reinstated", "counted_gossip", "off_by_one_regular", "other",
)
MISTAKES = BUCKETS[3:-1]  # the buckets a single, identifiable mistake gives

# "ANSWER: $810K", tolerant of markdown and "Final answer:"
ANSWER_LINE = re.compile(r"^[\s*_#>`-]*(?:final\s+)?answer[\s*_`]*:(.*)$", re.IGNORECASE | re.MULTILINE)
# "810", "$810K", "-$40K", "−40K", "$810,000", "810 thousand", "$1.2M"
NUMBER = re.compile(r"([-−])?\s*\$?\s*([-−])?(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|m|million)?\b", re.IGNORECASE)


def parse_answer(response: str | None) -> int | float | None:
    """The budget in $K from the last ANSWER line, or None when there is no answer line or no number."""
    text = response or ""
    matches = list(ANSWER_LINE.finditer(text))
    if not matches:
        return None
    body = matches[-1].group(1)
    if not NUMBER.search(body):  # "ANSWER:" with the number on the next line
        following = text[matches[-1].end():].strip().splitlines()
        body = following[0] if following else ""
    number = NUMBER.search(body)
    if not number:
        return None
    value = float(number[3].replace(",", ""))
    unit = (number[4] or "").lower()
    if unit in ("m", "million"):
        value *= 1000
    elif not unit and value >= 100_000:  # written in dollars, e.g. $810,000
        value /= 1000
    if number[1] or number[2]:
        value = -value
    return int(value) if value == int(value) else value


def hit_length_limit(usage: dict, stop_reason: str | None, max_output_tokens: int) -> bool:
    """The response reached the output limit: the CLI says so, Claude Code resumed past it, or the
    output is over max_output_tokens (which Codex cannot enforce, so its responses are measured too)."""
    reason = (stop_reason or "").lower()
    return ("max_tokens" in reason or "max_output_tokens" in reason or (usage.get("turns") or 1) > 1
            or (usage.get("output_tokens") or 0) > max_output_tokens)


def mistake_values(records: list[Record]) -> dict[str, list[dict]]:
    """Every answer one mistake gives on the full log, by bucket, with the records it points to."""
    answer = solvers.solve_backward(records)
    active = solvers.active_status(records)
    found: dict[str, dict[int, list[int]]] = {bucket: {} for bucket in MISTAKES}

    def add(bucket: str, value: int, record_id: int | None = None) -> None:
        ids = found[bucket].setdefault(value, [])
        if record_id is not None and record_id not in ids:
            ids.append(record_id)

    add("ignored_all_withdrawals", records[0].amount + sum(r.amount for r in records if r.kind == "adjust"))
    bottoms = set()
    for w in (r for r in records if r.kind == "withdraw"):
        # Mishandling any withdrawal in a chain flips the change at its bottom; that change is the match.
        bottom = w
        while bottom.kind == "withdraw":
            bottom = records[bottom.target - 1]
        bottoms.add(bottom.id)
        add("dropped_reinstated" if active[bottom.id] else "missed_withdrawal", solvers.flipped(records, w.id), bottom.id)
    for r in records:
        if r.kind == "gossip" and r.relative:
            add("counted_gossip", solvers.flipped(records, r.id), r.id)
        elif r.kind == "adjust" and r.id not in bottoms:
            dropped = solvers.flipped(records, r.id)
            add("off_by_one_regular", dropped, r.id)
            add("off_by_one_regular", 2 * answer - dropped, r.id)  # counted twice: the same |d|
    return {bucket: [{"value": v, "record_ids": ids} for v, ids in values.items()] for bucket, values in found.items()}


def score(response: str | None, key: dict, hit_limit: bool = False) -> dict:
    """key is a world's answer key (World.key): its answer and the values each mistake bucket holds."""
    value = parse_answer(response)
    answer = key["answer"]
    result = {"value": value, "expected": answer, "error": None if value is None else value - answer,
              "hit_length_limit": hit_limit, "record_ids": None}
    if value == answer:
        return {**result, "bucket": "correct", "correct": True}
    if value is None:
        return {**result, "bucket": "cut_off" if hit_limit else "gave_up", "correct": False}
    for bucket in MISTAKES:
        match = next((m for m in key["buckets"][bucket] if m["value"] == value), None)
        if match is not None:
            return {**result, "bucket": bucket, "correct": False, "record_ids": match["record_ids"]}
    return {**result, "bucket": "other", "correct": False}
