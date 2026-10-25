"""Checks every generated world must pass, scoring checks for validate, and the hand-worked logs."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

from experiment import solvers, text
from experiment.config import GeneratorSettings
from experiment.records import FINANCE, KEEPS_GOSSIP, VERSIONS, Record
from experiment.scoring import RECORD_SIGNATURES, UNIQUE_SIGNATURES, WITHDRAWAL_SIGNATURES, score
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
        # The two independent solvers must agree on every version.
        if solvers.solve_backward(records) != answer or solvers.solve_forward(records) != answer:
            problems.append(f"{version}: the two solvers do not both give {answer}")
        if ("gossip" in kinds) != (version in KEEPS_GOSSIP) or ("withdraw" in kinds) != (version in ("R", "RG")):
            problems.append(f"{version}: has the wrong kinds of records ({', '.join(sorted(kinds))})")
        problems += _check_rendering(records, version, answer)
        problems += _check_range(records, version, settings)

    if {c.active for c in world.chains} != {True, False}:
        problems.append("needs both a withdrawn change and one a withdrawal of a withdrawal reinstates")
    problems += _check_explicit(world)
    problems += _check_amounts(world, settings)
    problems += _check_signatures(world.key["signatures"])
    problems += _check_chain_mistakes(world)
    if world.project.lower() in text.VOCABULARY:
        problems.append(f"project name {world.project!r} is a word the log uses")
    return problems


def _check_rendering(records: list[Record], version: str, answer: int) -> list[str]:
    """The rendered text, read back using only the policy's wording, gives the same official records
    and the same answer, so the solvers and the prompt cannot disagree."""
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


def _check_range(records: list[Record], version: str, settings: GeneratorSettings) -> list[str]:
    """The budget a reader tracks while reading this version in order stays in range after every record.
    R, RG, and E share one: a change counts from when it appears until a withdrawal (or E's plain
    reversal) undoes it. C shows only the changes that survive, so a cancelled change never counts."""
    for r, budget in zip(records, solvers.running_budgets(records)):
        if not settings.budget_min <= budget <= settings.budget_max:
            return [f"{version}: running budget {budget} after #{r.id} is outside {settings.budget_min}-{settings.budget_max}"]
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


def _check_signatures(signatures: dict[str, list[dict]]) -> list[str]:
    """No collisions among the signatures built from unique sizes: each error points to one record,
    belongs to one signature, and is not the correct answer. Reset values and multiples of $5K are
    many-valued by nature and may overlap any signature; their coverage and the C and E baselines
    measure that instead."""
    owner: dict[int, str] = {}
    for name in UNIQUE_SIGNATURES:
        for entry in signatures[name]:
            error = entry["error"]
            if error == 0:
                return [f"a {name} answer equals the correct answer"]
            if len(entry["records"]) != 1:
                return [f"{name} error {error:+d} points to {len(entry['records'])} records"]
            if owner.setdefault(error, name) != name:
                return [f"error {error:+d} is both {owner[error]} and {name}"]
    return []


def _check_chain_mistakes(world: World) -> list[str]:
    """flipped() on any withdrawal in a chain must move the answer by exactly the change at its bottom:
    by its amount if it ends cancelled (counting it), by minus its amount if a withdrawal of a
    withdrawal restored it (dropping it)."""
    errors: dict[int, list[int]] = {}
    for name in WITHDRAWAL_SIGNATURES:
        for entry in world.key["signatures"][name]:
            for record_id in entry["records"]:
                errors.setdefault(record_id, []).append(entry["error"])
    problems = []
    for c in world.chains:
        expected = -c.amount if c.active else c.amount
        if errors.get(c.adjust_id) != [expected]:
            problems.append(f"chain at #{c.adjust_id}: mishandling it gives errors {errors.get(c.adjust_id)}, expected {expected:+d}")
    return problems


def check_scoring(world: World) -> list[str]:
    """Answers built to have each status and signature must score that way. Mistakes are also made for
    real, by changing one line and re-solving, to confirm a record matches its signature in every version."""
    key, answer = world.key, world.answer
    signatures = key["signatures"]
    # (response, hit the limit, status, a signature it must match, that match's candidate records)
    cases: list[tuple[str, bool, str, str | None, list[int] | None]] = [
        (f"ANSWER: ${answer}K", False, "correct", None, None), (f"ANSWER: ${answer}K", True, "correct", None, None),
        ("I cannot work this out.", False, "gave_up", None, None), ("Working through the records...", True, "cut_off", None, None),
    ]
    cases += [(f"ANSWER: ${answer + signatures[s][0]['error']}K", False, "wrong_number", s, signatures[s][0]["records"])
              for s in RECORD_SIGNATURES if signatures[s]]
    covered = {entry["error"] for s in RECORD_SIGNATURES for entry in signatures[s]}
    unmatched = next(e for e in range(1, 10 ** 6) if e % 5 and e not in covered)
    cases += [(f"ANSWER: ${answer + 5}K", False, "wrong_number", "multiple_of_5k", []),
              (f"ANSWER: ${answer + unmatched}K", False, "wrong_number", "unmatched", [])]

    def solved(version: str, record_id: int, **change) -> int:
        """The answer to a version with one record changed."""
        return solvers.solve_backward([replace(r, **change) if r.id == record_id else r for r in world.version(version)])

    as_filler = {"kind": "filler", "amount": None, "target": None}
    withdrawn = next(c for c in world.chains if not c.active)
    reinstated = next(c for c in world.chains if c.active)
    for c in (withdrawn, reinstated):
        name = "matches_restored_amount" if c.active else "matches_withdrawn_amount"
        # R: ignore the last withdrawal in the chain. E: skip the last explicit reversal.
        cases += [(f"ANSWER: ${solved(v, c.withdrawals[-1], **as_filler)}K", False, "wrong_number", name, [c.adjust_id]) for v in ("R", "E")]
    # C shows the reinstated change as an ordinary line; dropping it still matches the restored amount.
    cases.append((f"ANSWER: ${solved('C', reinstated.adjust_id, **as_filler)}K", False, "wrong_number",
                  "matches_restored_amount", [reinstated.adjust_id]))
    # RG: count one claimed change as if the Finance Office had made it.
    for claim in [r for r in world.records if r.kind == "gossip" and r.relative][:1]:
        cases.append((f"ANSWER: ${solved('RG', claim.id, kind='adjust', author=FINANCE)}K", False, "wrong_number",
                      "matches_relative_gossip", [claim.id]))

    problems = []
    for response, hit_limit, status, signature, ids in cases:
        got = score(response, key, hit_limit)
        matched = got["signatures"]
        if got["status"] != status or (signature is not None and matched.get(signature) != ids):
            problems.append(f"scoring: {response!r} is {got['status']} {matched}, expected {status} {signature or ''} {ids or ''}")
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
