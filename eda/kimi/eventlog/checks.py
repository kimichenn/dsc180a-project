"""Generator validation from the protocol: hand-written logs vs the resolver, and automatic checks on every generated log."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from eventlog.generator import Log, available_trap_types, single_trap_quota
from eventlog.resolver import Person, Policy, Record, counts, resolve

MAX_LENGTH_GAP = 0.03  # matched versions must be within 3% of each other in length


def check_log(log: Log) -> list[str]:
    """Every problem with one generated log pair; empty means it is usable."""
    problems = []
    planned = {p.name: p.planned for p in log.projects}
    if log.resolved("conflict") != planned:
        problems.append("resolver disagrees with the planned governing values (Conflict)")
    if log.resolved("consistent") != log.governing:
        problems.append("Consistent version resolves differently from Conflict")

    for p in log.projects:
        governing = log.governing.get(p.name)
        if governing is None or governing == log.threshold:
            problems.append(f"{p.name}: governing value missing or equal to the threshold")
            continue
        for kind, value in p.traps:
            if value == log.threshold or (value < log.threshold) == (governing < log.threshold):
                problems.append(f"{p.name}: {kind} trap {value} does not flip the threshold")
        if p.traps and log.budget_threshold is not None and p.budget <= log.budget_threshold:
            problems.append(f"{p.name}: trapped project fails the budget condition")

    quota = single_trap_quota(log.dials)
    for kind in available_trap_types(log.dials):
        singles = sum(1 for p in log.projects if [k for k, _ in p.traps] == [kind])
        if singles < quota:
            problems.append(f"only {singles} single-trap {kind} projects (need {quota})")

    conflict_text, consistent_text = log.render("conflict"), log.render("consistent")
    gap = abs(len(conflict_text) - len(consistent_text)) / len(conflict_text)
    if gap > MAX_LENGTH_GAP:
        problems.append(f"matched versions differ in length by {gap:.1%}")

    if {n.lower() for n in log.other_projects} & {p.name.lower() for p in log.projects}:
        problems.append("an out-of-program name matches an in-program name")
    problems += _check_records(log)
    return problems


def _check_records(log: Log) -> list[str]:
    problems = []
    records = {r.id: r for r in log.records("conflict")}
    people = log.people_by_name
    in_program = {p.name for p in log.projects}
    by_project: dict[str, list] = {}
    for e in log.events:
        if e.project in in_program:
            by_project.setdefault(e.project, []).append(e)

    for name, events in by_project.items():
        days = [e.date for e in events]
        if len(days) != len(set(days)):
            problems.append(f"{name}: two records on the same day")
        counting = [e for e in events if counts(records[e.id], log.policy, people)]
        last_counting = max(e.date for e in counting)
        for e in events:
            if e.trap in ("distractor", "pre_authority"):
                if counts(records[e.id], log.policy, people):
                    problems.append(f"{name}: {e.trap} record counts under the policy")
                if e.date <= last_counting:
                    problems.append(f"{name}: {e.trap} record is not after the last counting record")
            if e.kind == "retract":
                target = records.get(e.target)
                between = [c for c in counting if target and target.date < c.date < e.date]
                if target is None or target.project != name or not counts(target, log.policy, people):
                    problems.append(f"{name}: retraction does not point at a counting record of this project")
                elif log.policy.authority_on(target.date) != log.policy.authority_on(e.date):
                    problems.append(f"{name}: retraction crosses the authority handover")
                elif between:
                    problems.append(f"{name}: another counting change sits between a correction and its retraction")
    return problems


def check_hand_logs(path: Path) -> tuple[int, list[str]]:
    """Resolve each hand-written log and compare with the answer computed by hand."""
    problems = []
    cases = json.loads(Path(path).read_text())
    for case in cases:
        handover = case.get("handover")
        policy = Policy("Program Office", "Release Board" if handover else None, _day(handover) if handover else None)
        people = {
            p["name"]: Person(p["name"], p["office"], p.get("moves_to"), _day(p["move_date"]) if p.get("move_date") else None)
            for p in case["people"]
        }
        records = [
            Record(r["id"], _day(r["date"]), r["author"], r["op"], r["project"], _day(r["value"]) if r.get("value") else None, r.get("target"))
            for r in case["records"]
        ]
        resolved = resolve(records, policy, people, set(case["projects"]))
        expected = {name: _day(value) for name, value in case["expected"].items()}
        if resolved != expected:
            got = {k: v.isoformat() for k, v in resolved.items()}
            problems.append(f"{case['name']}: resolver gave {got}, hand answer {case['expected']}")
        threshold = _day(case["threshold"])
        answer = sorted(name for name, day in resolved.items() if day < threshold)
        if answer != sorted(case["answer"]):
            problems.append(f"{case['name']}: answer {answer}, hand answer {case['answer']}")
    return len(cases), problems


def _day(text: str) -> date:
    return date.fromisoformat(text)
