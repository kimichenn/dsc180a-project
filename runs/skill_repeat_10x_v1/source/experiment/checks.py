"""Checks every generated world must pass, scoring checks for validate, and the hand-worked logs."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

from experiment import solvers, text
from experiment.config import GeneratorSettings
from experiment.records import KEEPS_GOSSIP, VERSIONS, Record
from experiment.scoring import MISTAKES, score
from experiment.world import World


def check_world(world: World, settings: GeneratorSettings) -> list[str]:
    """Every problem with one world; empty means it is usable."""
    problems = solvers.check_structure(world.records)
    if problems:
        return problems
    answer = world.answer
    for version in VERSIONS:
        records = world.version(version)
        kinds = {r.kind for r in records}
        if solvers.check_structure(records):
            problems.append(f"{version}: {solvers.check_structure(records)[0]}")
            continue
        # Jeremy's two solvers must agree on every version.
        if solvers.solve_backward(records) != answer or solvers.solve_forward(records) != answer:
            problems.append(f"{version}: the two solvers do not both give {answer}")
        if ("gossip" in kinds) != (version in KEEPS_GOSSIP) or ("withdraw" in kinds) != (version in ("R", "RG")):
            problems.append(f"{version}: has the wrong kinds of records ({', '.join(sorted(kinds))})")
        problems += _check_rendering(records, version, answer)

    if {c.active for c in world.chains} != {True, False}:
        problems.append("needs both a withdrawn change and one a withdrawal of a withdrawal reinstates")
    problems += _check_explicit(world)
    problems += _check_amounts(world, settings)
    if not settings.chronological:
        problems += _check_buckets(world.key["buckets"], answer)
    problems += _check_chain_mistakes(world)

    if settings.chronological:
        problems += check_chronological_range(world.records, settings)
    else:
        budget = world.records[0].amount
        for r in world.records:
            if r.kind == "adjust" and world.active[r.id]:
                budget += r.amount
                if not settings.budget_min <= budget <= settings.budget_max:
                    problems.append(f"#{r.id}: true budget {budget} outside {settings.budget_min}-{settings.budget_max}")
                    break
    if world.project.lower() in text.VOCABULARY:
        problems.append(f"project name {world.project!r} is a word the log uses")
    return problems


def check_chronological_range(records: list[Record], settings: GeneratorSettings) -> list[str]:
    budget = 0
    for record, delta in solvers.replay(records):
        budget += delta
        if not settings.budget_min <= budget <= settings.budget_max:
            return [f"#{record.id}: chronological budget {budget} outside {settings.budget_min}-{settings.budget_max}"]
    return []


def _check_rendering(records: list[Record], version: str, answer: int) -> list[str]:
    """Kimi's v5 check: the rendered text, read back using only the policy's wording, gives the same
    official records and the same answer, so the solvers and the prompt cannot disagree."""
    try:
        parsed = text.parse_log(text.render_log(records))
    except ValueError as error:
        return [f"{version}: {error}"]
    for got, want in zip(parsed, records):
        same = (got.id, got.kind, got.author) == (want.id, want.kind, want.author)
        if same and want.kind in ("opening", "adjust", "withdraw"):
            same = (got.amount, got.target) == (want.amount, want.target)
        if not same:
            return [f"{version}: #{want.id} reads back as {got.kind} {got.amount or got.target}, generated as {want.kind}"]
    if len(parsed) != len(records) or {solvers.solve_backward(parsed), solvers.solve_forward(parsed)} != {answer}:
        return [f"{version}: rendered text does not resolve to {answer}"]
    return []


def _check_explicit(world: World) -> list[str]:
    """E is R line for line, except each withdrawal is a plain Finance change: the first withdrawal
    in a chain reverses the change at its bottom, the next re-applies it, and so on."""
    problems = [f"E: #{r.id} differs from R" for r, e in zip(world.version("R"), world.version("E")) if r.kind != "withdraw" and r != e]
    explicit = world.version("E")
    for c in world.chains:
        for k, wid in enumerate(c.withdrawals):
            want = -c.amount if k % 2 == 0 else c.amount
            got = explicit[wid - 1]
            if got.kind != "adjust" or got.author != world.records[wid - 1].author or got.amount != want:
                problems.append(f"E: #{wid} should be a Finance change of {want:+d}, is {got.kind} {got.amount}")
    return problems


def _check_amounts(world: World, settings: GeneratorSettings) -> list[str]:
    """Regular changes are multiples of amount_step. Changes a withdrawal touches and claimed changes
    are not, and no other record uses their size."""
    step = settings.amount_step
    touched = {c.adjust_id for c in world.chains}
    special = [r for r in world.records if r.id in touched or (r.kind == "gossip" and r.relative)]
    sizes = Counter(abs(r.amount) for r in world.records if r.kind == "adjust" or (r.kind == "gossip" and r.relative))
    problems = [f"#{r.id}: regular change {r.amount} is not a multiple of {step}"
                for r in world.records if r.kind == "adjust" and r.id not in touched and r.amount % step]
    problems += [f"#{r.id}: {r.kind} amount {r.amount} is a multiple of {step}" for r in special if r.amount % step == 0]
    problems += [f"#{r.id}: {r.kind} amount {abs(r.amount)} is used by another record" for r in special if sizes[abs(r.amount)] != 1]
    return problems


def _check_buckets(buckets: dict[str, list[dict]], answer: int) -> list[str]:
    """No bucket's values overlap another bucket's or equal the answer, so every wrong answer has one bucket."""
    owner: dict[int, str] = {}
    for bucket in MISTAKES:
        for match in buckets[bucket]:
            value = match["value"]
            if value == answer:
                return [f"a {bucket} answer equals the correct answer"]
            if owner.setdefault(value, bucket) != bucket:
                return [f"{value} is both {owner[value]} and {bucket}"]
    return []


def _check_chain_mistakes(world: World) -> list[str]:
    """flipped() on any withdrawal in a chain must move the answer by exactly the change at its
    bottom: +amount if it ends withdrawn, -amount if a withdrawal of a withdrawal restored it."""
    matches = [(i, m["value"]) for b in ("missed_withdrawal", "dropped_reinstated") for m in world.key["buckets"][b] for i in m["record_ids"]]
    by_change, counts = dict(matches), Counter(i for i, _ in matches)
    problems = []
    for c in world.chains:
        expected = world.answer + (-c.amount if c.active else c.amount)
        if counts[c.adjust_id] != 1 or by_change.get(c.adjust_id) != expected:
            problems.append(f"chain at #{c.adjust_id}: mishandling it gives {by_change.get(c.adjust_id)}, expected {expected}")
    return problems


def check_scoring(world: World) -> list[str]:
    """Answers built to land in each bucket must land there. Mistakes are also made for real, by
    removing one line and re-solving, to confirm a record keeps its bucket in every version."""
    key, answer = world.key, world.answer
    cases = [(f"ANSWER: ${answer}K", False, "correct", None), (f"ANSWER: ${answer}K", True, "correct", None),
             ("I cannot work this out.", False, "gave_up", None), ("Working through the records...", True, "cut_off", None)]
    cases += [(f"ANSWER: ${key['buckets'][b][0]['value']}K", False, b, None) for b in MISTAKES]

    def without(version: str, record_id: int) -> int:
        records = [replace(r, kind="filler", amount=None, target=None) if r.id == record_id else r for r in world.version(version)]
        return solvers.solve_backward(records)

    withdrawn = next(c for c in world.chains if not c.active)
    reinstated = next(c for c in world.chains if c.active)
    for c in (withdrawn, reinstated):
        bucket = "dropped_reinstated" if c.active else "missed_withdrawal"
        # R: ignore the last withdrawal in the chain. E: skip the last explicit reversal.
        cases += [(f"ANSWER: ${without(v, c.withdrawals[-1])}K", False, bucket, [c.adjust_id]) for v in ("R", "E")]
    # C shows the reinstated change as an ordinary line; dropping it is still dropped_reinstated.
    cases.append((f"ANSWER: ${without('C', reinstated.adjust_id)}K", False, "dropped_reinstated", [reinstated.adjust_id]))

    problems = []
    for response, hit_limit, want, ids in cases:
        got = score(response, key, hit_limit)
        if got["bucket"] != want or (ids is not None and got["record_ids"] != ids):
            problems.append(f"scoring: {response!r} is {got['bucket']} {got['record_ids']}, expected {want} {ids or ''}")
    return problems


def check_hand_logs(path: Path) -> tuple[list[dict], list[str]]:
    """(cases, problems). Each case's answer was worked out by hand from its lines; both solvers must match it."""
    cases = json.loads(Path(path).read_text())
    problems = []
    for case in cases:
        try:
            records = text.parse_lines(case["lines"])
        except ValueError as error:
            problems.append(f"{case['name']}: {error}")
            continue
        structure = solvers.check_structure(records)
        if structure:
            problems.append(f"{case['name']}: {structure[0]}")
            continue
        got = {solvers.solve_backward(records), solvers.solve_forward(records)}
        if got != {case["expected"]}:
            problems.append(f"{case['name']}: solvers gave {sorted(got)}, hand answer {case['expected']}")
    return cases, problems
