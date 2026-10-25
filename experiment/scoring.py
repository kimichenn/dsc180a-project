"""Read the number from a response, give the call an outcome status, and match a wrong number to error signatures.

Status (d = answer - correct budget):
    correct       d = 0
    wrong_number  an ANSWER line with any other number
    cut_off       hit the output limit with no number on an ANSWER line
    gave_up       refused, abstained, or otherwise no ANSWER line with a number
gave_up and cut_off count as wrong everywhere. A response that hit the output limit is still scored
on its final ANSWER line when it has one; hit_length_limit flags it, by the same rule for every model.

A wrong number is checked against every signature, and can match several:
    matches_withdrawn_amount       the answer counts one change a withdrawal cancelled (an odd chain depth)
    matches_restored_amount        the answer drops one change a withdrawal of a withdrawal restored (even depth)
    matches_relative_gossip        the answer applies the change one relative gossip claim states
    matches_absolute_gossip_reset  the answer is one claimed budget plus every surviving Finance change after it
    multiple_of_5k                 d is a multiple of $5K; regular changes all are, so it names no records
    unmatched                      none of the above
The first three are solvers.flipped's answer with that one record mishandled, so each d is the exact
signed effect of the mistake: counting a cancelled decrease makes the answer too low. Each match carries
its candidate records: the first three use sizes no other record has, so they have one each; a reset
value can come from several claims. Values come from each record's role in the full log and are
checked in every version, so C (no withdrawals or gossip) and E (the withdrawals' numbers without
their logic) show how often each signature matches by chance. A match is a pattern in the number,
never proof of the reasoning, and only the number is used, never the response text.
"""

from __future__ import annotations

import re

from experiment import solvers
from experiment.records import Record

STATUSES = ("correct", "wrong_number", "gave_up", "cut_off")
RECORD_SIGNATURES = (
    "matches_withdrawn_amount", "matches_restored_amount", "matches_relative_gossip", "matches_absolute_gossip_reset",
)
UNIQUE_SIGNATURES = RECORD_SIGNATURES[:3]  # built from sizes no other record uses
SIGNATURES = (*RECORD_SIGNATURES, "multiple_of_5k", "unmatched")
WITHDRAWAL_SIGNATURES = RECORD_SIGNATURES[:2]  # their matches carry the chain's depth

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


def signature_errors(records: list[Record]) -> dict[str, list[dict]]:
    """Every signed error each record signature covers on the full log, with its candidate records
    (and, for the withdrawal signatures, the chain's depth)."""
    found: dict[str, dict[int, dict]] = {name: {} for name in RECORD_SIGNATURES}

    def add(name: str, error: int, record_id: int, **extra: int) -> None:
        ids = found[name].setdefault(error, {"error": error, "records": [], **extra})["records"]
        if record_id not in ids:
            ids.append(record_id)

    answer = solvers.solve_backward(records)
    for chain in solvers.chains(records):
        name = "matches_restored_amount" if chain.active else "matches_withdrawn_amount"
        for wid in chain.withdrawals:  # mishandling any withdrawal in a chain flips the change at its bottom
            add(name, solvers.flipped(records, wid) - answer, chain.adjust_id, depth=chain.depth)
    active = solvers.active_status(records)
    surviving_after = 0  # the surviving Finance changes after the record being read, walking back from the end
    for r in reversed(records):
        if r.kind == "adjust" and active[r.id]:
            surviving_after += r.amount
        elif r.kind == "gossip" and r.relative:
            add("matches_relative_gossip", solvers.flipped(records, r.id) - answer, r.id)
        elif r.kind == "gossip":
            add("matches_absolute_gossip_reset", r.amount + surviving_after - answer, r.id)
    return {name: [values[error] for error in sorted(values)] for name, values in found.items()}


def index_signatures(signatures: dict[str, list[dict]]) -> dict[str, dict[int, dict]]:
    """A key's signature entries by error, for lookups."""
    return {name: {entry["error"]: entry for entry in signatures[name]} for name in RECORD_SIGNATURES}


def match_signatures(error: int | float, index: dict[str, dict[int, dict]]) -> tuple[dict[str, list[int]], int | None]:
    """The signatures a wrong number's error matches, each with its candidate records, and the depth
    of the withdrawal chain it points to (None if it points to none). index is from index_signatures."""
    matched: dict[str, list[int]] = {}
    depth = None
    for name in RECORD_SIGNATURES:
        entry = index[name].get(error)
        if entry is not None:
            matched[name] = entry["records"]
            depth = entry.get("depth", depth)
    if error == int(error) and int(error) % 5 == 0:
        matched["multiple_of_5k"] = []
    return matched or {"unmatched": []}, depth


def score(response: str | None, key: dict, hit_limit: bool = False) -> dict:
    """key is a world's answer key (World.key): its answer and the errors each signature covers."""
    value = parse_answer(response)
    answer = key["answer"]
    error = None if value is None else value - answer
    if value is None:
        status = "cut_off" if hit_limit else "gave_up"
    else:
        status = "correct" if error == 0 else "wrong_number"
    signatures, depth = match_signatures(error, index_signatures(key["signatures"])) if status == "wrong_number" else ({}, None)
    return {"status": status, "correct": status == "correct", "value": value, "expected": answer, "error": error,
            "hit_length_limit": hit_limit, "signatures": signatures, "chain_depth": depth}
