"""Generate a world: a budget log whose versions share one answer.

1. Layout: each position draws a record kind in proportion to how many of that kind are left. A
   withdrawal names an earlier withdrawal with probability nested_rate (when one is free), and
   otherwise an earlier adjustment, which the layout marks as withdrawn. Nothing is withdrawn
   twice and the opening never is.
2. Sizes: regular changes are multiples of $5K. Every change a withdrawal touches (withdrawn or
   reinstated) and every claimed change gets a size that is not a multiple of 5 and that no other
   record uses, so a wrong answer off by that size points to exactly one record. Gossip is half
   claimed figures, half claimed changes.
3. Walk: read the log in order, keeping two running budgets in range. R's is the one a reader of
   the full log tracks (solvers.Ledger): each change counts when it appears, and each withdrawal
   undoes or restores its change when it appears; RG and E share it. C's counts only the changes
   that survive, so cancelling a change removes it from C's budget from where it appeared onward.
   Each change is signed to keep R's budget in range and each claimed budget is drawn near it, so
   changes and gossip read as plausible where they appear. Each withdrawal names a random free
   record of its kind (a marked adjustment, or a withdrawal nothing has withdrawn yet) among those
   whose withdrawal keeps both budgets in range: with targets fixed in advance, undoing changes
   this large pushes nearly every long log out of range. If none fits, the log is resampled.
4. Wording comes from text.py. Each withdrawal also gets the plain change it makes when it
   arrives and a line for it, which version E shows instead of the withdrawal.
5. The answer always comes from the solvers, never from this plan, and generate() resamples
   until every check in checks.py passes.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from itertools import accumulate

from experiment import text
from experiment.checks import check_world
from experiment.config import GeneratorSettings
from experiment.records import FINANCE, Record
from experiment.solvers import Ledger
from experiment.world import World

MAX_ATTEMPTS = 200
FINANCE_FILLER_SHARE = 0.3  # share of filler records the Finance Office writes
OPENING_RANGE = (1000, 3000)  # $K, in steps of 10


def record_counts(settings: GeneratorSettings) -> dict[str, int]:
    n = settings.records
    counts = {
        "adjust": round(n * settings.adjust_share) - 1,  # the opening budget is the first Finance change
        "withdraw": round(n * settings.withdraw_share),
        "gossip": round(n * settings.gossip_share),
    }
    counts["filler"] = n - 1 - sum(counts.values())
    if counts["adjust"] < 2 or counts["withdraw"] < 2 or counts["filler"] < 0:
        raise ValueError(f"{n} records are too few for these shares")
    return counts


def generate(seed: int, settings: GeneratorSettings) -> World:
    """The world for (seed, number of records). The same pair always gives the same world."""
    record_counts(settings)  # fail fast on settings that can never work
    lo, hi = OPENING_RANGE
    if not settings.budget_min <= lo <= hi <= settings.budget_max:
        raise ValueError(f"the opening budget range {lo}-{hi} must sit inside the budget range")
    rng = random.Random(f"ledger-{seed}-{settings.records}")
    project = text.project_name(rng)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        world = _attempt(rng, seed, project, settings)
        if world is not None and not check_world(world, settings):
            world.attempts = attempt
            return world
    raise RuntimeError(f"no valid world for seed {seed} with {settings.records} records after {MAX_ATTEMPTS} attempts")


@dataclass(frozen=True)
class Layout:
    """Each position's record kind and role. Which record each withdrawal names is left to the walk."""

    kinds: list[str]
    withdrawn: set[int]  # adjustments a withdrawal will name: they get unique sizes
    nested: set[int]  # withdrawals that name an earlier withdrawal rather than an adjustment


def _layout(rng: random.Random, settings: GeneratorSettings) -> Layout | None:
    remaining = record_counts(settings)
    free: dict[str, list[int]] = {"adjust": [], "withdraw": []}  # records no withdrawal names yet
    kinds, withdrawn, nested = ["opening"], set(), set()
    for rid in range(2, settings.records + 1):
        options = [k for k, left in remaining.items() if left and (k != "withdraw" or free["adjust"] or free["withdraw"])]
        if not options:
            return None
        kind = rng.choices(options, weights=[remaining[k] for k in options])[0]
        remaining[kind] -= 1
        if kind == "withdraw":
            if free["withdraw"] and (not free["adjust"] or rng.random() < settings.nested_rate):
                free["withdraw"].pop(rng.randrange(len(free["withdraw"])))
                nested.add(rid)
            else:
                withdrawn.add(free["adjust"].pop(rng.randrange(len(free["adjust"]))))
        if kind in free:
            free[kind].append(rid)
        kinds.append(kind)
    return Layout(kinds, withdrawn, nested)


def _attempt(rng: random.Random, seed: int, project: str, settings: GeneratorSettings) -> World | None:
    layout = _layout(rng, settings)
    if layout is None:
        return None
    unique = _unique_sizes(rng, layout, settings)
    width = text.id_width(settings.records)
    ledger = Ledger()  # R's running budget
    history: list[int] = []  # C's running budget after each record so far, with every change as it now stands
    effects: dict[int, int] = {}  # how much each record moved R's budget when it arrived
    bottoms: dict[int, int] = {}  # each withdrawal's chain: the change at its bottom
    nameable: dict[str, list[int]] = {"adjust": [], "withdraw": []}  # records a withdrawal can still name
    records = []
    for rid, kind in enumerate(layout.kinds, 1):
        budget = ledger.budget  # the running budget before this record
        author, amount, target, is_relative = FINANCE, None, None, False
        if kind == "opening":
            amount = rng.randrange(OPENING_RANGE[0], OPENING_RANGE[1] + 1, 10)
            body = text.opening(rng, project, amount)
        elif kind == "adjust":
            size = unique.get(rid) or rng.randrange(settings.amount_step, settings.amount_max + 1, settings.amount_step)
            amount = _signed(rng, size, budget, settings)
            body = text.adjust(rng, project, amount)
        elif kind == "withdraw":
            target = _target(rng, nameable["withdraw" if rid in layout.nested else "adjust"], effects, bottoms, history, settings)
            if target is None:
                return None
            body = text.withdraw(rng, target, width)
        elif kind == "gossip":
            author, is_relative = rng.choice(text.OTHER_AUTHORS), rid in unique
            if is_relative:
                amount = _signed(rng, unique[rid], budget, settings)
                body = text.gossip_change(rng, project, amount)
            else:
                amount = _claim(rng, budget, settings)
                body = text.gossip_claim(rng, project, amount, budget)
        else:
            author = FINANCE if rng.random() < FINANCE_FILLER_SHARE else rng.choice(text.OTHER_AUTHORS)
            body = text.filler(rng, project, author)
        # What the line says when a version switches it off; opening and filler are never switched off.
        filler = text.filler_like(rng, project, author, body) if kind in ("adjust", "withdraw", "gossip") else ""
        record = Record(rid, kind, author, amount, target, is_relative, body, filler)
        effects[rid] = ledger.apply(record)
        if kind == "withdraw":
            record = replace(record, reversal=effects[rid], reversal_text=text.reversal(project, effects[rid], body))
            bottoms[rid] = bottoms.get(target, target)
            for i in range(bottoms[rid] - 1, len(history)):  # C's budget moves from the bottom change onward
                history[i] += effects[rid]
        if kind == "withdraw" or rid in layout.withdrawn:
            nameable[kind].append(rid)
        history.append(ledger.budget)  # C now counts what R counts: every change as it stands so far
        records.append(record)
    return World(f"s{seed}_n{settings.records}", seed, project, records)


def _target(rng: random.Random, nameable: list[int], effects: dict[int, int], bottoms: dict[int, int], history: list[int],
            settings: GeneratorSettings) -> int | None:
    """A random record from nameable whose withdrawal keeps both running budgets in range, taken off
    the list; None if every one would push one out. Nothing has withdrawn these records yet, so
    withdrawing one undoes exactly the effect it had when it arrived, and C's budget moves by that much
    from the change at the bottom of its chain to now. C's latest value is R's, so that span covers R too."""
    lows = list(accumulate(reversed(history), min))[::-1]  # lows[i]: C's lowest budget from record i + 1 to now
    highs = list(accumulate(reversed(history), max))[::-1]
    fits = [rid for rid in nameable
            if settings.budget_min <= lows[bottoms.get(rid, rid) - 1] - effects[rid]
            and highs[bottoms.get(rid, rid) - 1] - effects[rid] <= settings.budget_max]
    if not fits:
        return None
    target = rng.choice(fits)
    nameable.remove(target)
    return target


def _unique_sizes(rng: random.Random, layout: Layout, settings: GeneratorSettings) -> dict[int, int]:
    """A size no other record uses for each change a withdrawal names directly and each claimed
    change (the gossip drawn as relative), keyed by record id."""
    relative = {rid for rid, kind in enumerate(layout.kinds, 1) if kind == "gossip" and rng.random() < settings.relative_gossip_share}
    special = sorted(layout.withdrawn | relative)
    pool = [size for size in range(1, settings.unique_amount_max + 1) if size % settings.amount_step]
    if len(pool) < len(special):
        raise ValueError(
            f"{settings.records} records need {len(special)} unique amounts, but 1-{settings.unique_amount_max} has only "
            f"{len(pool)} that are not multiples of {settings.amount_step}; raise unique_amount_max"
        )
    return dict(zip(special, rng.sample(pool, len(special))))


def _signed(rng: random.Random, size: int, level: int, settings: GeneratorSettings) -> int:
    """Up or down by size from the running budget, pulled toward the middle of the budget range and
    never out of it. Withdrawn changes and claimed changes are signed the same way, so they look like the rest."""
    low, high = settings.budget_min, settings.budget_max
    up = rng.random() < (0.8 if level < low + 500 else 0.2 if level > high - 500 else 0.5)
    if not low <= level + (size if up else -size) <= high:
        up = not up
    return size if up else -size


def _claim(rng: random.Random, level: int, settings: GeneratorSettings) -> int:
    """A wrong but plausible budget figure: within -30% / +40% of the running budget and at least $20K away."""
    while True:
        claim = round(level * rng.uniform(0.7, 1.4) / 10) * 10
        claim = min(max(claim, settings.budget_min + 100), settings.budget_max - 200)
        if abs(claim - level) >= 20:
            return claim
