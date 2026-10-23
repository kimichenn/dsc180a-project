"""Checks every generated world must pass, and the hand-worked logs the solvers are checked against."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from experiment import solvers, text
from experiment.config import GeneratorSettings
from experiment.records import VERSIONS, has_gossip, has_withdrawals
from experiment.scoring import MISTAKES
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
        if ("gossip" in kinds) != has_gossip(version) or ("withdraw" in kinds) != has_withdrawals(version):
            problems.append(f"{version}: has the wrong kinds of records ({', '.join(sorted(kinds))})")
        problems += _check_rendering(records, version, answer)
        lures = world.key["lures"][version]
        applicable = (*solvers.WITHDRAWAL_LURES, "last_number") if has_withdrawals(version) else ("last_number",)
        problems += [f"{version}: lure {name} equals the answer" for name in applicable if lures[name] == answer]
        problems += _check_buckets(world.key["buckets"][version], version, answer)

    chains = world.chains
    if not any(c.depth == 1 for c in chains) or not any(c.depth > 1 for c in chains):
        problems.append("needs both a single withdrawal and a withdrawal of a withdrawal")
    problems += _check_amounts(world, settings)
    problems += _check_chain_mistakes(world)

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


def _check_rendering(records, version: str, answer: int) -> list[str]:
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


def _check_buckets(buckets: dict[str, list[dict]], version: str, answer: int) -> list[str]:
    """No bucket's values overlap another bucket's or equal the answer, so every wrong answer has one bucket."""
    owner: dict[int, str] = {}
    for bucket in MISTAKES:
        for match in buckets[bucket]:
            value = match["value"]
            if value == answer:
                return [f"{version}: a {bucket} answer equals the correct answer"]
            if owner.setdefault(value, bucket) != bucket:
                return [f"{version}: {value} is both {owner[value]} and {bucket}"]
    return []


def _check_chain_mistakes(world: World) -> list[str]:
    """flipped() on any withdrawal in a chain must move the answer by exactly the change at its
    bottom: +amount if it ends withdrawn, -amount if a withdrawal of a withdrawal restored it."""
    buckets = world.key["buckets"]["RG"]
    by_change = {i: m["value"] for b in ("missed_withdrawal", "dropped_reinstated") for m in buckets[b] for i in m["record_ids"]}
    counts = Counter(i for b in ("missed_withdrawal", "dropped_reinstated") for m in buckets[b] for i in m["record_ids"])
    problems = []
    for c in world.chains:
        expected = world.answer + (-c.amount if c.active else c.amount)
        if counts[c.adjust_id] != 1 or by_change.get(c.adjust_id) != expected:
            problems.append(f"chain at #{c.adjust_id}: mishandling it gives {by_change.get(c.adjust_id)}, expected {expected}")
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
