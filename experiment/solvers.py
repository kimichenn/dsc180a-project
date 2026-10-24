"""Two independent answer solvers, single-mistake answers, and withdrawal chains.

Both solvers read only each record's kind, amount, and target, never the generator's plan
(Jeremy's Exp 3):
- solve_backward resolves status from the newest record back (a record is active unless an
  active withdrawal names it), then adds every active adjustment to the opening budget.
- solve_forward replays the log in order; when a withdrawal arrives it toggles the record it
  names and every record down that record's chain of targets. The replay also gives what each
  withdrawal does to the budget when it arrives, which version E states as a plain change.

flipped (Kimi's v5) gives the answer with one record handled the wrong way. Scoring uses it to
name the single mistake behind a wrong answer.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from experiment.records import FINANCE, OFFICIAL, Record


@dataclass(frozen=True)
class Chain:
    """An adjustment and the withdrawals stacked on it: withdrawals[0] names the adjustment, each later one the one before."""

    adjust_id: int
    amount: int
    withdrawals: tuple[int, ...]
    active: bool  # whether the adjustment counts at the end of the log

    @property
    def depth(self) -> int:
        return len(self.withdrawals)


def check_structure(records: list[Record]) -> list[str]:
    """Every rule a log must follow; empty means both solvers can read it."""
    problems = []
    if [r.id for r in records] != list(range(1, len(records) + 1)):
        problems.append("record ids are not 1..N in order")
    if not records or records[0].kind != "opening":
        problems.append("record #1 does not set the opening budget")
    by_id: dict[int, Record] = {}
    targeted: set[int] = set()
    for r in records:
        if r.kind in OFFICIAL and r.author != FINANCE:
            problems.append(f"#{r.id}: {r.kind} written by {r.author}")
        if r.kind == "gossip" and r.author == FINANCE:
            problems.append(f"#{r.id}: gossip written by the Finance Office")
        if r.kind == "opening" and r.id != 1:
            problems.append(f"#{r.id}: a second opening budget")
        if r.kind in ("opening", "adjust", "gossip") and type(r.amount) is not int:
            problems.append(f"#{r.id}: {r.kind} amount {r.amount!r} is not an integer")
        if r.kind == "adjust" and r.amount == 0:
            problems.append(f"#{r.id}: adjustment of zero")
        if r.kind == "withdraw":
            target = by_id.get(r.target)
            if target is None or target.kind not in ("adjust", "withdraw"):
                problems.append(f"#{r.id}: target #{r.target} is not an earlier adjustment or withdrawal")
            if r.target in targeted:
                problems.append(f"#{r.target} is withdrawn twice")
            targeted.add(r.target)
        by_id[r.id] = r
    return problems


def active_status(records: list[Record], force: dict[int, bool] | None = None) -> dict[int, bool]:
    """Each adjustment's and withdrawal's status at the end of the log, resolved newest first.
    force pins chosen records' status; everything that depends on them follows."""
    withdrawn: set[int] = set()
    active = {}
    for r in reversed(records):
        if r.kind in ("adjust", "withdraw"):
            active[r.id] = force[r.id] if force and r.id in force else r.id not in withdrawn
            if r.kind == "withdraw" and active[r.id]:
                withdrawn.add(r.target)
    return active


def solve_backward(records: list[Record]) -> int:
    active = active_status(records)
    return records[0].amount + sum(r.amount for r in records if r.kind == "adjust" and active[r.id])


def replay(records: list[Record]) -> Iterator[tuple[Record, int]]:
    """Each record with how much it moves the budget when it arrives, replaying the log in order."""
    by_id: dict[int, Record] = {}
    active: dict[int, bool] = {}
    for r in records:
        by_id[r.id] = r
        delta = 0
        if r.kind in ("opening", "adjust"):
            active[r.id] = True
            delta = r.amount
        elif r.kind == "withdraw":
            active[r.id] = True
            target = r.target
            while True:
                active[target] = not active[target]
                victim = by_id[target]
                if victim.kind == "adjust":
                    delta = victim.amount if active[target] else -victim.amount
                    break
                target = victim.target
        yield r, delta


def solve_forward(records: list[Record]) -> int:
    return sum(delta for _, delta in replay(records))


def reversals(records: list[Record]) -> dict[int, int]:
    """What each withdrawal does to the budget when it arrives: it reverses or re-applies the change at the bottom of its chain."""
    return {r.id: delta for r, delta in replay(records) if r.kind == "withdraw"}


def flipped(records: list[Record], record_id: int) -> int:
    """The answer with one record's treatment flipped: a gossip claim applied as if the Finance
    Office wrote it, or an adjustment's or withdrawal's status reversed (everything that depends
    on it follows, so a mishandled withdrawal of a withdrawal flips the adjustment it restored)."""
    record = records[record_id - 1]
    active = active_status(records)
    if record.kind == "gossip":
        return _fold(records, active, gossip=record_id)
    if record.kind not in ("adjust", "withdraw"):
        raise ValueError(f"#{record_id} is {record.kind}; only gossip, adjustments, and withdrawals can flip")
    return _fold(records, active_status(records, force={record_id: not active[record_id]}))


def _fold(records: list[Record], active: dict[int, bool], gossip: int | None = None) -> int:
    """The opening budget, then every active adjustment in order; gossip names one claim to apply as well."""
    value = records[0].amount
    for r in records:
        if r.kind == "adjust" and active[r.id]:
            value += r.amount
        elif r.id == gossip:
            value = value + r.amount if r.relative else r.amount
    return value


def chains(records: list[Record]) -> list[Chain]:
    withdrawn_by = {r.target: r.id for r in records if r.kind == "withdraw"}
    active = active_status(records)
    out = []
    for r in records:
        if r.kind == "adjust" and r.id in withdrawn_by:
            stack, current = [], r.id
            while current in withdrawn_by:
                current = withdrawn_by[current]
                stack.append(current)
            out.append(Chain(r.id, r.amount, tuple(stack), active[r.id]))
    return out
