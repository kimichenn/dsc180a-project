"""Generator validation: hand chains vs the resolver, and the v5 guarantees on every generated chain.

parse_records reads records back from rendered text using only the policy's wording, so the
round trip also checks that rendering says what the generator meant.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from chain.dials import Profile
from chain.generator import HIGH, LOW, VOCABULARY, Chain
from chain.resolver import COUNTING, FINANCE, LURES, Record, counts, is_update, resolve

LINE = re.compile(r"^#(\d+)\s+(\d{4}-\d{2}-\d{2})\s+(.+?):\s+(.*)$")
SET_TEXT = re.compile(r"\bbudget set to \$(\d[\d,]*)K\b")
ADJUST_TEXT = re.compile(r"\bbudget (increased|decreased) by \$(\d[\d,]*)K\b")
WITHDRAW_ID_TEXT = re.compile(r"^Withdraw update #(\d+)\b")
WITHDRAW_DESCRIPTION_TEXT = re.compile(r"^Withdraw the (\d{4}-\d{2}-\d{2}) ")


def applicable_lures(profile: Profile) -> list[str]:
    """Lures that can differ from the answer under this profile (the others match it by design)."""
    waived = set()
    if not profile.nested_withdraw:
        waived.add("ignore_nested")
    if profile.withdraw_target == "latest":
        waived.add("withdraw_pops_latest")
    return [name for name in LURES if name not in waived]


def check_chain(chain: Chain) -> list[str]:
    """Every problem with one generated chain; empty means it is usable."""
    problems = []
    conflict, control = chain.records("conflict"), chain.records("control")
    if not len(conflict) == len(control) == chain.n:
        problems.append(f"record counts {len(conflict)} / {len(control)}, expected {chain.n}")
    if chain.resolved("control") != chain.answer:
        problems.append(f"control resolves to {chain.resolved('control')}, conflict to {chain.answer}")

    lures = chain.lures("conflict")
    for name in applicable_lures(chain.profile):
        if lures[name] == chain.answer:
            problems.append(f"lure {name} equals the answer ({chain.answer})")

    own = [r for r in conflict if r.entity == chain.project]
    for op in ("note", "withdraw"):
        if not any(chain.consequential[r.id] for r in own if r.op == op):
            problems.append(f"no consequential {op}")

    problems += _check_structure(conflict)
    problems += _check_values(conflict, chain.active)
    days = [e.day for e in chain.entries]
    if any(a >= b for a, b in zip(days, days[1:])):
        problems.append("dates do not strictly increase")
    problems += _check_names(chain.entities)
    problems += _check_rendering(chain)
    return problems


def _check_structure(records: list[Record]) -> list[str]:
    problems = []
    if [r.id for r in records] != list(range(1, len(records) + 1)):
        problems.append("record ids are not 1..N in order")
    if records[0].op != "set":
        problems.append("record #1 is not a set")
    by_id = {r.id: r for r in records}
    first: dict[str, int] = {}
    targeted: set[int] = set()
    for r in records:
        first.setdefault(r.entity, r.id)
        if (r.op in COUNTING) != (r.author == FINANCE and r.op != "neutral"):
            problems.append(f"#{r.id}: {r.op} written by {r.author}")
        if first[r.entity] == r.id and r.op != "set":
            problems.append(f"#{r.id}: {r.entity}'s first record is not a set")
        if r.op != "withdraw":
            continue
        target = by_id.get(r.target)
        if target is None or target.id >= r.id or not counts(target):
            problems.append(f"#{r.id}: target #{r.target} is not an earlier counting record")
        elif target.entity != r.entity:
            problems.append(f"#{r.id}: target #{r.target} belongs to another project")
        elif target.id == first[target.entity]:
            problems.append(f"#{r.id}: withdraws {target.entity}'s first set")
        if r.target in targeted:
            problems.append(f"#{r.target} is withdrawn twice")
        targeted.add(r.target)
    return problems


def _check_values(records: list[Record], active: dict[int, bool]) -> list[str]:
    """True budgets in range at every step; notes always disagree with the true budget."""
    problems = []
    value: dict[str, int] = {}
    for r in records:
        current = value.get(r.entity)
        if r.op in ("set", "adjust", "note") and not isinstance(r.amount, int):
            problems.append(f"#{r.id}: amount {r.amount!r} is not an integer")
            continue
        if r.op == "set" and r.amount <= 0 or r.op == "adjust" and r.amount == 0:
            problems.append(f"#{r.id}: {r.op} amount {r.amount}")
        if r.op == "note" and (r.amount == 0 if r.relative else r.amount == current):
            problems.append(f"#{r.id}: note agrees with the true budget {current}")
        if is_update(r) and active[r.id]:
            value[r.entity] = r.amount if r.op == "set" else current + r.amount
            if not LOW <= value[r.entity] <= HIGH:
                problems.append(f"#{r.id}: {r.entity} budget {value[r.entity]} outside {LOW}-{HIGH}")
    return problems


def _check_names(names: list[str]) -> list[str]:
    problems = []
    lowered = [n.lower() for n in names]
    for name in lowered:
        if not re.fullmatch(r"[a-z]+", name) or name in VOCABULARY:
            problems.append(f"project name {name!r} is not a fresh single word")
        if any(name != other and name in other for other in lowered):
            problems.append(f"project name {name!r} is part of another name")
    return problems


def _check_rendering(chain: Chain) -> list[str]:
    problems = []
    for version in ("conflict", "control"):
        text = chain.render(version)
        head, _, body = text.partition("\n\nRECORDS\n")
        if not body or not head.startswith("POLICY"):
            problems.append(f"{version}: missing POLICY or RECORDS section")
            continue
        try:
            parsed, _ = parse_records(body.splitlines(), chain.entities)
        except ValueError as error:
            problems.append(f"{version}: {error}")
            continue
        expected = chain.records(version)
        for got, want in zip(parsed, expected):
            same = (got.id, got.op, got.entity) == (want.id, want.op, want.entity)
            if same and counts(want):
                same = (got.amount, got.target) == (want.amount, want.target)
            if not same:
                problems.append(f"{version}: #{want.id} reads back as {got}, generated as {want}")
                break
        if len(parsed) != len(expected) or resolve(parsed, chain.project) != chain.answer:
            problems.append(f"{version}: rendered text does not resolve to {chain.answer}")
    return problems


def parse_records(lines: list[str], names: list[str]) -> tuple[list[Record], list[date]]:
    """Records read back from rendered lines. Notes keep no amount: only counting records matter here."""
    records: list[Record] = []
    days: list[date] = []
    by_id: dict[int, Record] = {}
    id_by_day: dict[date, int] = {}
    for line in lines:
        m = LINE.match(line.strip())
        if not m:
            raise ValueError(f"unreadable record line {line!r}")
        rid, day, author, text = int(m[1]), date.fromisoformat(m[2]), m[3], m[4]
        entity = next((name for name in names if re.search(rf"\b{name}\b", text)), None)
        official = author == FINANCE
        if official and (w := WITHDRAW_ID_TEXT.match(text) or WITHDRAW_DESCRIPTION_TEXT.match(text)):
            target = int(w[1]) if w.re is WITHDRAW_ID_TEXT else id_by_day.get(date.fromisoformat(w[1]))
            if target not in by_id:
                raise ValueError(f"#{rid} withdraws a record that is not earlier in the log")
            record = Record(rid, author, "withdraw", by_id[target].entity, target=target)
        elif official and (s := SET_TEXT.search(text)):
            record = Record(rid, author, "set", entity, int(s[1].replace(",", "")))
        elif official and (a := ADJUST_TEXT.search(text)):
            sign = 1 if a[1] == "increased" else -1
            record = Record(rid, author, "adjust", entity, sign * int(a[2].replace(",", "")))
        elif official and re.search(r"\$|budget|withdraw", text, re.IGNORECASE):
            raise ValueError(f"#{rid}: Finance Office line matches no update pattern: {text!r}")
        else:
            record = Record(rid, author, "note" if "$" in text else "neutral", entity)
        if record.entity is None:
            raise ValueError(f"#{rid} names no known project: {text!r}")
        records.append(record)
        days.append(day)
        by_id[rid] = record
        id_by_day[day] = rid
    return records, days


def check_hand_chains(path: Path) -> tuple[int, list[str], list[str]]:
    """(chains, problems, names still waiting for a hand answer). A pending chain's resolver
    answer is not shown, so whoever fills it in works it out independently."""
    cases = json.loads(Path(path).read_text())
    problems, pending = [], []
    for case in cases:
        names = [case["project"], *case.get("other_projects", [])]
        try:
            records, days = parse_records(case["lines"], names)
        except ValueError as error:
            problems.append(f"{case['name']}: {error}")
            continue
        if [r.id for r in records] != list(range(1, len(records) + 1)) or any(a >= b for a, b in zip(days, days[1:])):
            problems.append(f"{case['name']}: ids must run 1..N and dates must strictly increase")
        if case.get("expected") is None:
            pending.append(case["name"])
            continue
        got = resolve(records, case["project"])
        if got != case["expected"]:
            problems.append(f"{case['name']}: resolver gave {got}, hand answer {case['expected']}")
    return len(cases), problems, pending


def summary(chain: Chain) -> dict:
    """Numbers for reading a chain's difficulty: how much of it the answer actually depends on."""
    own = [r for r in chain.records("conflict") if r.entity == chain.project]
    ops = {r.id: r.op for r in own}
    last_set = max(i for i, r in enumerate(own) if r.op == "set" and chain.active[r.id])
    conflict, control = chain.render("conflict"), chain.render("control")
    return {
        "records": len(own),
        "consequential": sum(chain.consequential[r.id] for r in own),
        "after_last_set": len(own) - 1 - last_set,
        "nested": sum(1 for r in own if r.op == "withdraw" and ops[r.target] == "withdraw"),
        "length_gap": (len(control) - len(conflict)) / len(conflict),
        "chars": len(conflict),
    }
