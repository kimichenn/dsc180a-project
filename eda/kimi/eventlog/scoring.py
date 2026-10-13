"""Parse the final ANSWER line and score each in-program project as a correct or wrong decision."""

from __future__ import annotations

import re

from eventlog.generator import TRAP_TYPES

_ANSWER_LINE = re.compile(r"^[\s*_#>`-]*(?:final\s+)?answer[\s*_`]*:(.*)$", re.IGNORECASE | re.MULTILINE)
_SEPARATORS = re.compile(r",|;|\band\b", re.IGNORECASE)


def normalize_name(name: str) -> str:
    """Case, whitespace, surrounding punctuation, and a leading 'Project'."""
    name = re.sub(r"[*_`\"'.\[\]()]", " ", name).strip().lower()
    name = re.sub(r"^project\s+", "", name)
    return re.sub(r"\s+", " ", name)


def parse_answer(response: str | None) -> list[str] | None:
    """Names from the last ANSWER line, [] for 'none', or None when there is no answer line."""
    text = response or ""
    matches = list(_ANSWER_LINE.finditer(text))
    if not matches:
        return None
    body = matches[-1].group(1).strip()
    if not normalize_name(body):  # "ANSWER:" with the names on the next line
        following = text[matches[-1].end() :].strip().splitlines()
        body = following[0] if following else ""
    if not normalize_name(body):
        return None
    if normalize_name(body) == "none":
        return []
    return [n for n in (normalize_name(part) for part in _SEPARATORS.split(body)) if n]


def score_call(names: list[str], meta: dict) -> dict:
    """Decision-level scores for one parsed answer against the log's metadata."""
    predicted = set(names)
    in_program = {normalize_name(p["name"]) for p in meta["projects"]}
    other = {normalize_name(n) for n in meta["other_projects"]}
    scores = {"n": len(meta["projects"]), "wrong": 0, "trapped_n": 0, "trapped_wrong": 0, "untrapped_n": 0, "untrapped_wrong": 0}
    for kind in TRAP_TYPES:
        scores[f"single_{kind}_n"] = scores[f"single_{kind}_wrong"] = 0

    for project in meta["projects"]:
        wrong = (normalize_name(project["name"]) in predicted) != project["included"]
        scores["wrong"] += wrong
        group = "trapped" if project["traps"] else "untrapped"
        scores[f"{group}_n"] += 1
        scores[f"{group}_wrong"] += wrong
        if len(project["traps"]) == 1:
            kind = project["traps"][0]["type"]
            scores[f"single_{kind}_n"] += 1
            scores[f"single_{kind}_wrong"] += wrong  # every trap sits across the threshold, so wrong = adopted

    scores["error_rate"] = scores["wrong"] / scores["n"]
    scores["out_of_program"] = len(predicted & other)
    scores["invented"] = len(predicted - in_program - other)
    scores["exact"] = scores["wrong"] == 0 and scores["out_of_program"] == 0 and scores["invented"] == 0
    return scores
