"""Scenario and filler records, loaded from the JSON files in data/."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

SUBTYPES = ("non_authoritative_distractor", "superseding_update")
FORMATS = ("multi_document", "multi_turn")
QUESTION_TYPES = ("direct", "one_step", "two_step")
DEFAULT_CONFIDENCE_CUE = "This has been confirmed with the whole team."


@dataclass(frozen=True)
class Claim:
    source: str
    date: date
    text: str  # sentence with a {value} slot
    value: str = ""  # empty for the rung-4 extra claim, which borrows its value

    def render(self, value: str) -> str:
        return self.text.format(value=value)


@dataclass(frozen=True)
class AnswerKey:
    """Accepted answer strings under the governing and the non-governing claim."""

    correct: tuple[str, ...]
    nongoverning: tuple[str, ...]


@dataclass(frozen=True)
class Paraphrase:
    """Rung 2: text that replaces the later claim, stated relative to the earlier one."""

    conflict: str
    consistent: str


@dataclass(frozen=True)
class Scenario:
    id: str
    domain: str
    format: str
    conflict_subtype: str
    source_rule: str
    governing: Claim
    competing: Claim
    supporting_source: str
    supporting_text: str
    inference_rule: str
    questions: dict[str, str]
    answers: dict[str, AnswerKey]
    paraphrase: Paraphrase | None = None
    confidence_cue: str = DEFAULT_CONFIDENCE_CUE
    extra_competing: Claim | None = None

    @property
    def governing_is_earlier(self) -> bool:
        return self.governing.date < self.competing.date

    @property
    def later_role(self) -> str:
        """Role ("governing" or "competing") of the chronologically second claim."""
        return "competing" if self.governing_is_earlier else "governing"

    @property
    def earlier_value(self) -> str:
        return self.governing.value if self.governing_is_earlier else self.competing.value

    @property
    def max_rung(self) -> int:
        """Highest difficulty rung this record has the fields for."""
        if self.paraphrase is None:
            return 1
        if self.extra_competing is None:
            return 3
        return 4

    def expected_answers(self, question_type: str, variant: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """(expected, alternative) answers for one trial.

        In the Consistent variant the later claim repeats the earlier claim's value, so
        the expected answer is whatever the earlier claim implies. For updates that is
        the value the conflict version marks as non-governing.
        """
        key = self.answers[question_type]
        if variant == "conflict" or self.governing_is_earlier:
            return key.correct, key.nongoverning
        return key.nongoverning, key.correct


@dataclass(frozen=True)
class FillerPassage:
    id: str
    source: str
    text: str

    @property
    def words(self) -> int:
        return len(self.text.split())

    @property
    def approx_tokens(self) -> int:
        return round(len(self.text) / 4)


def _strings(value: str | list[str]) -> tuple[str, ...]:
    return (value,) if isinstance(value, str) else tuple(value)


def _claim(record: dict) -> Claim:
    return Claim(
        source=record["source"],
        date=date.fromisoformat(record["date"]),
        text=record["text"],
        value=record.get("value", ""),
    )


def parse_scenario(record: dict) -> Scenario:
    try:
        ladder = record.get("ladder", {})
        paraphrase = ladder.get("paraphrase")
        extra = ladder.get("extra_competing_claim")
        return Scenario(
            id=record["id"],
            domain=record["domain"],
            format=record["format"],
            conflict_subtype=record["conflict_subtype"],
            source_rule=record["source_rule"],
            governing=_claim(record["governing_claim"]),
            competing=_claim(record["competing_claim"]),
            supporting_source=record["supporting_fact"]["source"],
            supporting_text=record["supporting_fact"]["text"],
            inference_rule=record["inference_rule"],
            questions={q: record[f"q_{q}"] for q in QUESTION_TYPES},
            answers={
                q: AnswerKey(
                    correct=_strings(record[f"answers_{q}"]["correct"]),
                    nongoverning=_strings(record[f"answers_{q}"]["nongoverning"]),
                )
                for q in QUESTION_TYPES
            },
            paraphrase=Paraphrase(**paraphrase) if paraphrase else None,
            confidence_cue=ladder.get("confidence_cue", DEFAULT_CONFIDENCE_CUE),
            extra_competing=_claim(extra) if extra else None,
        )
    except KeyError as missing:
        raise ValueError(f"scenario {record.get('id', '?')!r} is missing field {missing}") from None


def load_scenarios(path: Path) -> list[Scenario]:
    return [parse_scenario(record) for record in json.loads(Path(path).read_text())]


def load_filler(path: Path) -> list[FillerPassage]:
    return [FillerPassage(**record) for record in json.loads(Path(path).read_text())]
