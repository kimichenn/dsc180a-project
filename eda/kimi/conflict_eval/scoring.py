"""Labelling responses: normalize and string-match first, then a hand-label queue for the rest.

Labels follow the proposal: correct, adopted_nongoverning, no_answer, other_error. The
separate flag for whether the response mentions the conflict is always automatic: conflict
or source-authority wording, or both values named in a direct answer.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

LABELS = ("correct", "adopted_nongoverning", "no_answer", "other_error")
LABELS_FILE = "labels.jsonl"

_MONTHS = {
    "jan": "january", "feb": "february", "mar": "march", "apr": "april", "jun": "june",
    "jul": "july", "aug": "august", "sep": "september", "sept": "september",
    "oct": "october", "nov": "november", "dec": "december",
}
_MONTH_ABBREVIATION = re.compile(r"\b(" + "|".join(_MONTHS) + r")\b\.?")
# Patterns run on normalized text, so apostrophes are already gone ("can't" -> "can t").
_HEDGE = re.compile(
    r"\b(cannot|can t|unable to|not possible to|impossible to) (be )?(determine|determined|resolve|resolved|tell|say)\b"
    r"|\b(not enough|insufficient) information\b|\bambiguous\b|\bunclear\b"
)
_CONFLICT_TERMS = re.compile(
    r"\b(conflict\w*|contradict\w*|discrepan\w*|inconsisten\w*|disagree\w*|unverified|supersed\w*|overrid\w*|outdated)\b"
)
# Runs on raw text. Allows closing markdown or quotes ("**Falcon.**"). Semicolons don't end
# a sentence, so "notes say X; database says Y" stays whole.
_SENTENCE_END = re.compile(r"[.!?:][*_'\"’”)]*(?=\s|$)|\n")
_PARENTHETICAL = re.compile(r"\([^()]*\)")


def normalize(text: str) -> str:
    """Lowercase, unify dates and numbers, and turn punctuation into spaces."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)  # 1,200 -> 1200
    text = re.sub(r"\b(\d+)(st|nd|rd|th)\b", r"\1", text)  # 18th -> 18
    text = _MONTH_ABBREVIATION.sub(lambda m: _MONTHS[m.group(1)], text)  # Oct. -> october
    text = re.sub(r"[^\w\s]|_", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def mentions_any(normalized_text: str, answers: list[str] | tuple[str, ...]) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(normalize(a))}(?!\w)", normalized_text) for a in answers)


@dataclass(frozen=True)
class AutoScore:
    label: str | None  # None: needs a human
    mentions_conflict: bool


def auto_score(
    response: str, expected: list[str], alternative: list[str], variant: str, question_type: str = "direct"
) -> AutoScore:
    """Label a response only when the string match is unambiguous.

    Exactly one of the two candidate answers present -> correct / adopted (other_error in
    the Consistent variant, where there is no non-governing claim). Both present but the
    first sentence names only the expected one -> correct; comparison answers usually name
    both options, and lead with the one they pick. Neither present but a clear hedge ->
    no_answer. Anything else, including a first sentence that leads with the other option,
    goes to the hand-label queue, so every adoption with both options named gets a human look.
    """
    text = normalize(response)
    has_expected = mentions_any(text, expected)
    has_alternative = mentions_any(text, alternative)
    hedged = _HEDGE.search(text) is not None
    # Naming both options only signals the conflict for direct questions; comparisons name both entities anyway.
    both_values = question_type == "direct" and has_expected and has_alternative
    mentions_conflict = both_values or _CONFLICT_TERMS.search(text) is not None

    if hedged:
        label = "no_answer" if not (has_expected or has_alternative) else None
    elif has_expected and not has_alternative:
        label = "correct"
    elif has_alternative and not has_expected:
        label = alternative_label(variant)
    elif has_expected and _leads_with(response, expected, alternative):
        label = "correct"
    else:
        label = None
    return AutoScore(label, mentions_conflict)


def _leads_with(response: str, answers: list[str], others: list[str]) -> bool:
    """True if the first sentence, minus parentheticals, names one of `answers` and none of `others`."""
    first_sentence = _SENTENCE_END.split(response.strip(), maxsplit=1)[0]
    lead = normalize(_PARENTHETICAL.sub(" ", first_sentence))
    return mentions_any(lead, answers) and not mentions_any(lead, others)


def alternative_label(variant: str) -> str:
    """Label for a response that gave the other option."""
    return "adopted_nongoverning" if variant == "conflict" else "other_error"


def load_labels(run_dir: Path) -> dict[str, dict]:
    """Hand labels keyed by trial id. A later label for the same trial replaces an earlier one."""
    path = Path(run_dir) / LABELS_FILE
    if not path.exists():
        return {}
    labels = {}
    for line in path.read_text().splitlines():
        if line.strip():
            record = json.loads(line)
            labels[record["trial_id"]] = record
    return labels


def append_label(run_dir: Path, trial_id: str, label: str) -> None:
    if label not in LABELS:
        raise ValueError(f"unknown label {label!r}")
    record = {"trial_id": trial_id, "label": label, "labeled_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with open(Path(run_dir) / LABELS_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")


def score_rows(rows: list[dict], labels: dict[str, dict]) -> list[dict]:
    """Attach label, mentions_conflict, and label_source (hand / auto / pending) to each response row."""
    scored = []
    for row in rows:
        auto = auto_score(row["response"] or "", row["expected"], row["alternative"], row["variant"], row["question_type"])
        hand = labels.get(row["trial_id"])
        if hand:
            label, source = hand["label"], "hand"
        elif auto.label:
            label, source = auto.label, "auto"
        else:
            label, source = None, "pending"
        scored.append({**row, "label": label, "mentions_conflict": auto.mentions_conflict, "label_source": source})
    return scored
