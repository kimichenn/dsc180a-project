"""Apply the policy memo's rules to a log's records to get each project's governing launch date.

Rules (from the memo and policy update):
- Only the authoritative office sets launch dates: the first authority before the handover,
  the second authority from the handover date on.
- A record counts only if its author's office held that authority on the record's date.
- A later counting record replaces earlier ones. Notes never change a date.
- A retraction restores the value that the retracted record replaced.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Person:
    name: str
    office: str
    moves_to: str | None = None
    move_date: date | None = None

    def office_on(self, day: date) -> str:
        return self.moves_to if self.move_date is not None and day >= self.move_date else self.office


@dataclass(frozen=True)
class Policy:
    first_authority: str
    second_authority: str | None = None
    handover: date | None = None

    def authority_on(self, day: date) -> str:
        return self.second_authority if self.handover is not None and day >= self.handover else self.first_authority


@dataclass(frozen=True)
class Record:
    """What the resolver needs from one record: op is assign, retract, or none (a note)."""

    id: int
    date: date
    author: str
    op: str
    project: str
    value: date | None = None
    target: int | None = None


def counts(record: Record, policy: Policy, people: dict[str, Person]) -> bool:
    return record.op != "none" and people[record.author].office_on(record.date) == policy.authority_on(record.date)


def resolve(records: list[Record], policy: Policy, people: dict[str, Person], projects: set[str]) -> dict[str, date]:
    value: dict[str, date | None] = {}
    replaced: dict[int, date | None] = {}  # counting record id -> the value it replaced
    for record in sorted(records, key=lambda r: (r.date, r.id)):
        if record.project not in projects or not counts(record, policy, people):
            continue
        if record.op == "assign":
            replaced[record.id] = value.get(record.project)
            value[record.project] = record.value
        elif record.op == "retract" and record.target in replaced:
            value[record.project] = replaced[record.target]
    return {project: day for project, day in value.items() if day is not None}
