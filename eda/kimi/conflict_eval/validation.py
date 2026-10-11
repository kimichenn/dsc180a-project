"""Automatic scenario checks. They back up the by-hand checklist in the proposal; they do not replace it.

Checklist items 1-3 (the rule is unambiguous, each question has one answer, swapping
claims flips the answers) need a human reading. This module checks what it can: the
record structure, that the answers flip, that questions never restate a claim value,
that the Consistent and Conflict prompts differ only in the claim(s) they should
(item 4), and that filler mentions nothing scenario-relevant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import product

from conflict_eval.prompts import DISTANCES, DOC_ORDERS, RULE_PLACEMENTS, Condition, build_blocks
from conflict_eval.scenarios import FORMATS, QUESTION_TYPES, SUBTYPES, FillerPassage, Scenario
from conflict_eval.scoring import normalize


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def render(self) -> str:
        lines = []
        for title, items in (("Errors", self.errors), ("Warnings", self.warnings), ("Notes", self.notes)):
            if items:
                lines.append(f"{title}:")
                lines += [f"  - {item}" for item in items]
        return "\n".join(lines) or "All checks passed."


def validate(scenarios: list[Scenario], filler: list[FillerPassage]) -> ValidationReport:
    report = ValidationReport()
    ids = [s.id for s in scenarios]
    for duplicate in sorted({i for i in ids if ids.count(i) > 1}):
        report.errors.append(f"duplicate scenario id {duplicate!r}")
    for scenario in scenarios:
        _check_record(scenario, report)
        if not any(e.startswith(f"{scenario.id}:") for e in report.errors):
            _check_matched_variants(scenario, filler, report)
    _check_filler(scenarios, filler, report)
    _describe_balance(scenarios, report)
    return report


def _check_record(s: Scenario, report: ValidationReport) -> None:
    def error(message: str) -> None:
        report.errors.append(f"{s.id}: {message}")

    if s.format not in FORMATS:
        error(f"format must be one of {FORMATS}")
    if s.conflict_subtype not in SUBTYPES:
        error(f"conflict_subtype must be one of {SUBTYPES}")
    for claim in (s.governing, s.competing):
        if "{value}" not in claim.text:
            error(f"claim text from {claim.source!r} has no {{value}} slot")
    if normalize(s.governing.value) == normalize(s.competing.value):
        error("governing and competing claims carry the same value")
    if s.governing.date == s.competing.date:
        error("governing and competing claims need different dates")
    if s.conflict_subtype == "superseding_update" and s.governing_is_earlier:
        error("a superseding update must be dated after the claim it replaces")

    for q in QUESTION_TYPES:
        key = s.answers[q]
        if not key.correct or not key.nongoverning:
            error(f"answers_{q} needs both a correct and a nongoverning answer")
        elif {normalize(a) for a in key.correct} & {normalize(a) for a in key.nongoverning}:
            error(f"answers_{q}: the answer does not flip between the two claims")
        question = normalize(s.questions[q])
        for value in (s.governing.value, s.competing.value):
            if _contains(question, value):
                error(f"q_{q} restates the claim value {value!r}")
    direct = {normalize(a) for a in s.answers["direct"].correct}
    if normalize(s.governing.value) not in direct:
        report.warnings.append(f"{s.id}: governing value {s.governing.value!r} is not listed in answers_direct.correct")

    if s.extra_competing is not None:
        if "{value}" not in s.extra_competing.text:
            error("ladder.extra_competing_claim text has no {value} slot")
        dates = [s.governing.date, s.competing.date, s.extra_competing.date]
        if len(set(dates)) < 3:
            error("ladder.extra_competing_claim needs its own date")
        elif sorted(dates).index(s.governing.date) == 1:
            error("ladder.extra_competing_claim must sit on the same side of the governing claim as the competing claim")
    if s.max_rung < 4:
        missing = "ladder.paraphrase" if s.paraphrase is None else "ladder.extra_competing_claim"
        report.notes.append(f"{s.id}: supports rungs 0-{s.max_rung} (add {missing} for higher rungs)")


def _check_matched_variants(s: Scenario, filler: list[FillerPassage], report: ValidationReport) -> None:
    """Checklist item 4: Consistent and Conflict prompts differ only in the claims they should."""
    allowed_roles = {s.later_role, "extra"}
    orders = DOC_ORDERS if s.format == "multi_document" else ("forward",)
    for rung, distance, placement, order in product(range(s.max_rung + 1), DISTANCES, RULE_PLACEMENTS, orders):
        if 2 * (2 if rung >= 1 else 1) > len(filler):
            continue  # reported by _check_filler
        pair = [
            build_blocks(s, Condition(variant, "direct", distance, placement, "none", rung, order), filler)
            for variant in ("consistent", "conflict")
        ]
        changed = [a for a, b in zip(*pair) if a != b]
        where = f"rung {rung}, distance={distance}, rule={placement}, order={order}"
        if len(pair[0]) != len(pair[1]):
            report.errors.append(f"{s.id}: matched variants have different structure ({where})")
        elif not changed:
            report.errors.append(f"{s.id}: Consistent and Conflict prompts are identical ({where})")
        elif any(block.role not in allowed_roles for block in changed):
            report.errors.append(f"{s.id}: matched variants differ outside the later claim ({where})")


def _check_filler(scenarios: list[Scenario], filler: list[FillerPassage], report: ValidationReport) -> None:
    if len(filler) < 4:
        report.warnings.append(f"only {len(filler)} filler passages; rung 1 and above need 4")
    for passage in filler:
        text = normalize(passage.text)
        if re.search(r"\d", passage.text):
            report.warnings.append(f"filler {passage.id!r} contains digits (first round uses plain filler)")
        for s in scenarios:
            for term in _scenario_terms(s):
                if _contains(text, term):
                    report.errors.append(f"filler {passage.id!r} mentions {term!r} from scenario {s.id}")
        report.notes.append(f"filler {passage.id!r}: {passage.words} words, ~{passage.approx_tokens} tokens (chars/4)")


def _describe_balance(scenarios: list[Scenario], report: ValidationReport) -> None:
    def count(values: list[str]) -> str:
        return ", ".join(f"{v}={values.count(v)}" for v in sorted(set(values)))

    report.notes.append(f"subtypes: {count([s.conflict_subtype for s in scenarios])}")
    report.notes.append(f"formats: {count([s.format for s in scenarios])}")
    report.notes.append(f"domains: {count([s.domain for s in scenarios])}")
    first_named = sum(_correct_option_named_first(s) for s in scenarios)
    report.notes.append(f"one-step correct answer is the first-named option in {first_named}/{len(scenarios)} scenarios")
    governing_first = sum(s.governing_is_earlier for s in scenarios)
    report.notes.append(f"governing claim is the earlier-dated claim in {governing_first}/{len(scenarios)} scenarios")


def _correct_option_named_first(s: Scenario) -> bool:
    question = normalize(s.questions["one_step"])
    positions = {
        side: min((question.find(normalize(a)) for a in answers if normalize(a) in question), default=-1)
        for side, answers in (("correct", s.answers["one_step"].correct), ("other", s.answers["one_step"].nongoverning))
    }
    return 0 <= positions["correct"] < positions["other"] or positions["other"] < 0 <= positions["correct"]


def _scenario_terms(s: Scenario) -> set[str]:
    claims = [s.governing, s.competing] + ([s.extra_competing] if s.extra_competing else [])
    terms = {c.source for c in claims} | {s.supporting_source, s.governing.value, s.competing.value}
    for key in s.answers.values():
        terms |= set(key.correct) | set(key.nongoverning)
    return {t for t in terms if t}


def _contains(normalized_text: str, phrase: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(normalize(phrase))}(?!\w)", normalized_text) is not None
