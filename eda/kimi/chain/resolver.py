"""The oracle for a project's budget, plus the wrong-strategy resolvers that give each lure value.

Oracle rules (the policy text in the prompt says the same):
1. A record counts only if it comes from the Finance Office and is a set, adjust, or withdraw.
2. Status runs from the newest record backward: a counting record is active unless an active
   withdraw targets it. So withdrawing a withdrawal restores what it withdrew.
3. The budget is a fold over the project's active set/adjust records in record order, starting
   from its first set. A withdrawn record counts as if it never happened.
"""

from __future__ import annotations

from dataclasses import dataclass

FINANCE = "Finance Office"
UPDATES = ("set", "adjust")
COUNTING = ("set", "adjust", "withdraw")
LURES = ("notes_count", "ignore_withdrawals", "withdraw_pops_latest", "ignore_nested", "last_number")


@dataclass(frozen=True)
class Record:
    id: int
    author: str
    op: str  # set | adjust | withdraw | note | neutral
    entity: str
    amount: int | None = None  # set or absolute note: the budget in $K; adjust or relative note: the signed change
    relative: bool = False  # notes only: amount is a change, not a budget
    target: int | None = None  # withdraw only: id of the withdrawn record (same entity)


def counts(record: Record) -> bool:
    return record.author == FINANCE and record.op in COUNTING


def is_update(record: Record) -> bool:
    return record.op in UPDATES and counts(record)


def active_status(records: list[Record], nested: bool = True, force: dict[int, bool] | None = None) -> dict[int, bool]:
    """Every counting record's status, newest first. nested=False makes withdrawals of withdrawals
    do nothing; force pins chosen records' status (used to flip one record)."""
    ops = {r.id: r.op for r in records}
    withdrawn_by: dict[int, list[int]] = {}
    active = {}
    for r in reversed(records):
        if not counts(r):
            continue
        if force and r.id in force:
            active[r.id] = force[r.id]
        else:
            active[r.id] = not any(active[w] for w in withdrawn_by.get(r.id, ()))
        if r.op == "withdraw" and (nested or ops.get(r.target) != "withdraw"):
            withdrawn_by.setdefault(r.target, []).append(r.id)
    return active


def fold(records: list[Record], entity: str, active: dict[int, bool], notes: set[int] | bool = ()) -> int:
    """Apply the entity's active updates in order. notes: ids of notes treated as official (True = all)."""
    value = None
    for r in records:
        if r.entity != entity:
            continue
        if is_update(r) and active[r.id]:
            relative = r.op == "adjust"
        elif r.op == "note" and (notes is True or r.id in notes):
            relative = r.relative
        else:
            continue
        if relative:
            if value is None:
                raise ValueError(f"#{r.id}: change to {entity} before any set")
            value += r.amount
        else:
            value = r.amount
    if value is None:
        raise ValueError(f"{entity}: no budget set")
    return value


def resolve(records: list[Record], entity: str) -> int:
    return fold(records, entity, active_status(records))


def lures(records: list[Record], entity: str) -> dict[str, int]:
    """The answer each wrong strategy gives."""
    everything = {r.id: True for r in records if counts(r)}
    return {
        "notes_count": fold(records, entity, active_status(records), notes=True),
        "ignore_withdrawals": fold(records, entity, everything),
        "withdraw_pops_latest": _pops_latest(records, entity),
        "ignore_nested": fold(records, entity, active_status(records, nested=False)),
        "last_number": _last_number(records, entity),
    }


def _pops_latest(records: list[Record], entity: str) -> int:
    """Each withdrawal undoes the entity's most recent still-applied update, whatever it names.
    The first set is never undone, so there is always a budget."""
    applied = []
    for r in records:
        if r.entity == entity and is_update(r):
            applied.append(r)
        elif r.entity == entity and counts(r) and len(applied) > 1:
            applied.pop()
    return fold(applied, entity, {r.id: True for r in applied})


def _last_number(records: list[Record], entity: str) -> int:
    """The last dollar figure written about the entity (a change counts as its size)."""
    figures = [r.amount for r in records if r.entity == entity and r.op in ("set", "adjust", "note") and r.amount is not None]
    return abs(figures[-1])


def flipped(records: list[Record], entity: str, record_id: int) -> int:
    """The answer with one record's treatment flipped: a note applied as official, or a counting
    record's status reversed (everything that depends on it follows)."""
    record = next(r for r in records if r.id == record_id)
    active = active_status(records)
    if record.op == "note":
        return fold(records, entity, active, notes={record_id})
    if not counts(record):
        raise ValueError(f"#{record_id} is {record.op}; only notes and counting records can flip")
    return fold(records, entity, active_status(records, force={record_id: not active[record_id]}))


def consequential(records: list[Record], entity: str) -> dict[int, bool]:
    """For each of the entity's records, whether flipping it alone changes the answer.

    Same result as resolve(...) != flipped(...), in linear time. Assumes no record is withdrawn
    twice (the generator guarantees it), so flipping a withdrawal flips every record down its
    chain of targets and ends by flipping one update.
    """
    active = active_status(records)
    by_id = {r.id: r for r in records}
    own = [r for r in records if r.entity == entity]
    before, value = {}, None  # the budget just before each record
    for r in own:
        before[r.id] = value
        if is_update(r) and active[r.id]:
            value = r.amount if r.op == "set" else value + r.amount
    masked, later_set = {}, False  # an active set later on erases this record's effect
    for r in reversed(own):
        masked[r.id] = later_set
        later_set = later_set or (r.op == "set" and is_update(r) and active[r.id])

    def matters(r: Record) -> bool:
        if masked[r.id]:
            return False
        relative = r.op == "adjust" or (r.op == "note" and r.relative)
        return r.amount != 0 if relative else r.amount != before[r.id]

    out = {}
    for r in own:
        if r.op == "withdraw" and counts(r):
            end = r
            while end.op == "withdraw":
                end = by_id[end.target]
            out[r.id] = matters(end)
        else:
            out[r.id] = (is_update(r) or r.op == "note") and matters(r)
    return out
