"""Two independent answer solvers, the running budget, single-mistake answers, and withdrawal chains.

Both solvers read only each record's kind, amount, and target, never the generator's plan:
- solve_backward resolves status from the newest record back (a record is active unless an
  active withdrawal names it), then adds every active adjustment to the opening budget.
- solve_forward replays the log in order (Ledger); when a withdrawal arrives it toggles the record it
  names and every record down that record's chain of targets.

The forward replay is also the running budget a reader tracks: each change counts when it appears,
and each withdrawal undoes or restores its change when it appears. The generator steers that budget
and the checks keep it in range, and what each withdrawal does to it when it arrives is the plain
change version E states instead.

flipped gives the answer with one record handled the wrong way. Scoring uses it for the signatures
that point to one record, so each carries the exact signed effect of that mistake.
"""

from __future__ import annotations

from dataclasses import dataclass

from experiment.records import FINANCE, OFFICIAL, Record


@dataclass(frozen=True)
class Chain:
    """An adjustment and the withdrawals stacked on it: withdrawals[0] names the adjustment, each later one the one before."""

    adjust_id: int
    amount: int
    withdrawals: tuple[int, ...]
    active: bool  # whether the adjustment counts at the end of the log: restored (even depth) or cancelled (odd)

    @property
    def depth(self) -> int:
        return len(self.withdrawals)


class Ledger:
    """The budget while the log is read in order, one record at a time."""

    def __init__(self) -> None:
        self.budget = 0
        self._records: dict[int, Record] = {}
        self._active: dict[int, bool] = {}

    def apply(self, record: Record) -> int:
        """Read one more record and return how much it moves the budget."""
        self._records[record.id] = record
        delta = 0
        if record.kind in ("opening", "adjust"):
            self._active[record.id] = True
            delta = record.amount
        elif record.kind == "withdraw":
            self._active[record.id] = True
            target = record.target
            while True:  # each withdrawal down the chain flips, until the change at its bottom
                self._active[target] = not self._active[target]
                victim = self._records[target]
                if victim.kind == "adjust":
                    delta = victim.amount if self._active[target] else -victim.amount
                    break
                target = victim.target
        self.budget += delta
        return delta


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


def running_budgets(records: list[Record]) -> list[int]:
    """The budget after each record, reading the log in order."""
    ledger = Ledger()
    budgets = []
    for r in records:
        ledger.apply(r)
        budgets.append(ledger.budget)
    return budgets


def solve_forward(records: list[Record]) -> int:
    return running_budgets(records)[-1]


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
