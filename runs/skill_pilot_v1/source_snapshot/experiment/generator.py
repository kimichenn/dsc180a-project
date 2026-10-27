"""Generate a world: a budget log whose versions share one answer.

1. Layout (Jeremy's Exp 3): each position draws a record kind in proportion to how many of that
   kind are left. A withdrawal names a random earlier adjustment, or, with probability
   nested_rate, an earlier withdrawal. Nothing is withdrawn twice and the opening never is.
2. Amounts (Kimi's v5): walk forward so the true budget stays in range. Gossip is half claimed
   figures near the true budget, half claimed changes. Regular changes are multiples of $5K. Every
   change a withdrawal touches (withdrawn or reinstated) and every claimed change gets a size that
   is not a multiple of 5 and that no other record uses, so a wrong answer off by that size points
   to exactly one record.
3. Wording comes from text.py. Each withdrawal also gets the plain change it amounts to (from
   the forward replay) and a line for it, which version E shows instead of the withdrawal.
4. The answer always comes from the solvers, never from this plan, and generate() resamples
   until every check in checks.py passes.
"""

from __future__ import annotations

import random
from dataclasses import replace

from experiment import text
from experiment.checks import check_world
from experiment.config import GeneratorSettings
from experiment.records import FINANCE, Record
from experiment.solvers import active_status, reversals
from experiment.world import World

MAX_ATTEMPTS = 200
FINANCE_FILLER_SHARE = 0.3  # share of filler records the Finance Office writes
OPENING_RANGE = (500, 2000)  # $K, in steps of 10


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


def _layout(rng: random.Random, settings: GeneratorSettings) -> list[tuple[str, int | None]] | None:
    """Each record's kind and, for a withdrawal, the id it names."""
    remaining = record_counts(settings)
    free: dict[str, list[int]] = {"adjust": [], "withdraw": []}  # records no withdrawal names yet
    layout: list[tuple[str, int | None]] = [("opening", None)]
    for rid in range(2, settings.records + 1):
        kinds = [k for k, left in remaining.items() if left and (k != "withdraw" or free["adjust"] or free["withdraw"])]
        if not kinds:
            return None
        kind = rng.choices(kinds, weights=[remaining[k] for k in kinds])[0]
        remaining[kind] -= 1
        target = None
        if kind == "withdraw":
            nested = bool(free["withdraw"]) and (not free["adjust"] or rng.random() < settings.nested_rate)
            pool = free["withdraw"] if nested else free["adjust"]
            target = pool.pop(rng.randrange(len(pool)))
        if kind in free:
            free[kind].append(rid)
        layout.append((kind, target))
    return layout


def _attempt(rng: random.Random, seed: int, project: str, settings: GeneratorSettings) -> World | None:
    layout = _layout(rng, settings)
    if layout is None:
        return None
    skeleton = [Record(rid, kind, FINANCE, target=target) for rid, (kind, target) in enumerate(layout, 1)]
    active = active_status(skeleton)
    # The changes a withdrawal touches (the ones a withdrawal names directly) and the claimed changes.
    bottoms = {target for kind, target in layout if kind == "withdraw" and layout[target - 1][0] == "adjust"}
    relative = {rid for rid, (kind, _) in enumerate(layout, 1) if kind == "gossip" and rng.random() < settings.relative_gossip_share}
    special = sorted(bottoms | relative)
    pool = [size for size in range(1, settings.unique_amount_max + 1) if size % settings.amount_step]
    if len(pool) < len(special):
        raise ValueError(
            f"{settings.records} records need {len(special)} unique amounts, but 1-{settings.unique_amount_max} has only "
            f"{len(pool)} that are not multiples of {settings.amount_step}; raise unique_amount_max"
        )
    unique = dict(zip(special, rng.sample(pool, len(special))))

    width = text.id_width(settings.records)
    budget = rng.randrange(OPENING_RANGE[0], OPENING_RANGE[1] + 1, 10)
    records = []
    for rid, (kind, target) in enumerate(layout, 1):
        author, amount, is_relative = FINANCE, None, False
        if kind == "opening":
            amount = budget
            body = text.opening(rng, project, amount)
        elif kind == "adjust":
            size = unique.get(rid) or rng.randrange(settings.amount_step, settings.amount_max + 1, settings.amount_step)
            amount = _signed(rng, size, budget, settings)
            if active[rid]:
                budget += amount
            body = text.adjust(rng, project, amount)
        elif kind == "withdraw":
            body = text.withdraw(rng, target, width)
        elif kind == "gossip":
            author, is_relative = rng.choice(text.OTHER_AUTHORS), rid in relative
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
        records.append(Record(rid, kind, author, amount, target, is_relative, body, filler))
    effects = reversals(records)
    records = [replace(r, reversal=effects[r.id], reversal_text=text.reversal(project, effects[r.id], r.text)) if r.kind == "withdraw" else r
               for r in records]
    return World(f"s{seed}_n{settings.records}", seed, project, records)


def _signed(rng: random.Random, size: int, level: int, settings: GeneratorSettings) -> int:
    """Up or down by size, pulled toward the middle of the budget range and never out of it.
    Withdrawn changes and claimed changes are signed the same way, so they look like the rest."""
    low, high = settings.budget_min, settings.budget_max
    up = rng.random() < (0.8 if level < low + 500 else 0.2 if level > high - 500 else 0.5)
    if not low <= level + (size if up else -size) <= high:
        up = not up
    return size if up else -size


def _claim(rng: random.Random, level: int, settings: GeneratorSettings) -> int:
    """A wrong but plausible budget figure: within -30% / +40% of the true one and at least $20K away."""
    while True:
        claim = round(level * rng.uniform(0.7, 1.4) / 10) * 10
        claim = min(max(claim, settings.budget_min + 100), settings.budget_max - 200)
        if abs(claim - level) >= 20:
            return claim
