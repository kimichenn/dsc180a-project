"""Generate a v5 budget chain and render its conflict and control versions.

Each project gets a layout of record types (its first record is always a set), withdrawal
targets, then amounts picked walking forward so the true budget stays in range. Projects'
records are interleaved when there are several. The answer always comes from the resolver, and
generate() resamples until every check in checks.py passes.
"""

from __future__ import annotations

import random
import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from functools import cached_property

from chain.dials import Profile
from chain.resolver import FINANCE, UPDATES, Record, active_status, consequential, is_update, lures, resolve
from harness.names import codenames

START_DAY = date(2025, 9, 2)
LOW, HIGH = 200, 3000  # the true budget stays in this range ($K)
NESTED_SHARE = 0.25  # chance a withdrawal names an earlier withdrawal when one is available
RELATIVE_NOTE_SHARE = 0.5  # share of notes that state a change rather than a figure (when relative_notes)
NEUTRAL_FINANCE_SHARE = 0.3  # share of neutral records the Finance Office writes
MAX_ATTEMPTS = 500

POLICY = (
    "POLICY\n"
    "Only the Finance Office can change a project's budget. Messages from anyone else do not change it.\n"
    "The Finance Office can withdraw one of its earlier updates. A withdrawn update counts as if it never happened; "
    "every other update still applies, in order. A withdrawal can itself be withdrawn."
)
OTHER_AUTHORS = (
    "Engineering email", "PMO note", "Vendor call", "Operations chat",
    "Legal email", "Sales update", "Facilities ticket", "Marketing email",
)

# Templates take p (project), v (amount in $K), and a direction word chosen from (up, down) pairs.
SET = ("{p} budget set to ${v}K.", "{p} budget set to ${v}K after review.", "{p} budget set to ${v}K per the revised plan.")
ADJUST = (
    ("{p} budget {d} by ${v}K.", "increased", "decreased"),
    ("{p} budget {d} by ${v}K after review.", "increased", "decreased"),
    ("{p} budget {d} by ${v}K per the revised plan.", "increased", "decreased"),
)
WITHDRAW_ID = ("Withdraw update #{t}.", "Withdraw update #{t}; it was entered in error.")
WITHDRAW_DESCRIPTION = ("Withdraw the {t}.", "Withdraw the {t}; it was entered in error.")
NOTE_ABSOLUTE = (
    ("{p} budget is going {d} to ${v}K.", "up", "down"),
    ("{p} budget is going to ${v}K.", "", ""),
    ("Heard {p}'s budget is now ${v}K.", "", ""),
    ("{p} budget should land at ${v}K.", "", ""),
    ("Pretty sure {p}'s budget is ${v}K now.", "", ""),
)
NOTE_RELATIVE = (
    ("Hearing {p}'s budget goes {d} ${v}K.", "up", "down"),
    ("{p} budget is going {d} by ${v}K.", "up", "down"),
    ("Expect {p}'s budget to {d} by ${v}K.", "rise", "drop"),
    ("Sounds like {p} gets ${v}K {d}.", "more", "less"),
)
# Non-budget facts: no dollar figures, and none of the words the budget records use.
NEUTRAL = (
    "{p} kickoff moved to Building {n}.",
    "{p} design review moved to Room {room}.",
    "{p} weekly sync moved to {day}s.",
    "{p} status report filed for week {week}.",
    "{p} vendor onboarding call scheduled for {day}.",
    "{p} test environment back online.",
    "{p} demo rescheduled to {day} afternoon.",
    "{p} security review passed.",
    "{p} site visit confirmed for {day}.",
    "{p} risk register updated with {n} new items.",
    "{p} sprint {week} retrospective notes posted.",
    "{p} documentation moved to the shared drive.",
)
NEUTRAL_FINANCE = (
    "{p} invoice batch {code} archived.",
    "{p} quarterly audit scheduled for {day}.",
    "{p} cost center code changed to {code}.",
    "Reminder: {p} expense reports are due {day}.",
    "{p} purchase order {code} closed.",
    "{p} finance review moved to Room {room}.",
)
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")


def _vocabulary() -> set[str]:
    texts = [POLICY, FINANCE, *OTHER_AUTHORS, *SET, *WITHDRAW_ID, *WITHDRAW_DESCRIPTION, *NEUTRAL, *NEUTRAL_FINANCE, *WEEKDAYS]
    texts += [" ".join(t) for t in ADJUST + NOTE_ABSOLUTE + NOTE_RELATIVE] + ["budget setting increase decrease withdrawal"]
    return set(re.findall(r"[a-z]+", " ".join(texts).lower()))


VOCABULARY = _vocabulary()


@dataclass(frozen=True)
class Entry:
    record: Record
    day: date
    text: str  # what the record says after "Author: " in the conflict version
    neutral_text: str  # what it says instead if the control version replaces it


@dataclass
class Chain:
    seed: int
    n: int
    profile: Profile
    project: str  # the entity the question asks about
    entities: list[str]
    entries: list[Entry]
    attempts: int = 1
    _cache: dict = field(default_factory=dict, repr=False)

    @cached_property
    def active(self) -> dict[int, bool]:
        return active_status(self.records("conflict"))

    def kept(self, record: Record) -> bool:
        """Whether the control version keeps this record: neutral records and active updates."""
        return record.op == "neutral" or (is_update(record) and self.active[record.id])

    def records(self, version: str) -> list[Record]:
        if version not in self._cache:
            conflict = [e.record for e in self.entries]
            if version == "conflict":
                self._cache[version] = conflict
            else:
                self._cache[version] = [r if self.kept(r) else Record(r.id, r.author, "neutral", r.entity) for r in conflict]
        return self._cache[version]

    @cached_property
    def answer(self) -> int:
        return resolve(self.records("conflict"), self.project)

    def resolved(self, version: str) -> int:
        return resolve(self.records(version), self.project)

    def lures(self, version: str = "conflict") -> dict[str, int]:
        return lures(self.records(version), self.project)

    @cached_property
    def consequential(self) -> dict[int, bool]:
        return consequential(self.records("conflict"), self.project)

    @property
    def question(self) -> str:
        return f"What is {self.project}'s budget now?"

    @property
    def id_width(self) -> int:
        return max(3, len(str(self.n)))

    def render(self, version: str) -> str:
        lines = ["RECORDS"]
        for e in self.entries:
            text = e.text if version == "conflict" or self.kept(e.record) else e.neutral_text
            lines.append(f"#{e.record.id:0{self.id_width}d}  {e.day.isoformat()}  {e.record.author}: {text}")
        return f"{POLICY}\n\n" + "\n".join(lines)

    def metadata(self) -> dict:
        records = []
        for e in self.entries:
            r = e.record
            records.append({
                "id": r.id, "date": e.day.isoformat(), "author": r.author, "entity": r.entity, "op": r.op,
                "amount": r.amount, "relative": r.relative, "target": r.target,
                "active": self.active.get(r.id), "consequential": self.consequential.get(r.id, False),
                "control_op": r.op if self.kept(r) else "neutral",
            })
        return {
            "seed": self.seed,
            "n": self.n,
            "profile": asdict(self.profile),
            "project": self.project,
            "entities": self.entities,
            "question": self.question,
            "answer": self.answer,
            "lures": {"conflict": self.lures("conflict"), "control": self.lures("control")},
            "attempts": self.attempts,
            "records": records,
        }


def generate(n: int, profile: Profile, seed: int) -> Chain:
    """The chain for (n, seed). Profiles that change only wording share the same chain."""
    from chain.checks import check_chain  # checks reads generator constants

    rng = random.Random(f"chain-{seed}-{n}")
    names = _names(rng, profile.n_entities)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        chain = _attempt(rng, n, profile, seed, names)
        if chain is not None:
            chain.attempts = attempt
            if not check_chain(chain):
                return chain
    raise RuntimeError(f"no valid chain for n={n} seed={seed} after {MAX_ATTEMPTS} attempts")


def _names(rng: random.Random, count: int) -> list[str]:
    """v4 codenames that are not template words and do not contain one another."""
    taken: set[str] = set()
    names: list[str] = []
    while len(names) < count:
        name = codenames(rng, 1, taken)[0].lower()
        if name in VOCABULARY or any(name in other.lower() or other.lower() in name for other in names):
            continue
        names.append(name.capitalize())
    return names


def _layout(rng: random.Random, count: int, profile: Profile) -> list[tuple[str, int | None]] | None:
    """One entity's record types in order, with each withdrawal's target as a position in the list."""
    n_note = max(1, round(profile.note_rate * count))
    # With nesting, one withdrawal can restore another, so three keep at least one update withdrawn.
    n_withdraw = max(3 if profile.nested_withdraw else 1, round(profile.withdraw_rate * count))
    n_neutral = round(profile.neutral_rate * count)
    n_update = count - 1 - n_note - n_withdraw - n_neutral
    if n_update < 2:
        raise ValueError(f"{count} records per project are too few for this profile")
    n_adjust = round(profile.relative_rate * n_update)
    ops = ["note"] * n_note + ["withdraw"] * n_withdraw + ["neutral"] * n_neutral
    ops += ["adjust"] * n_adjust + ["set"] * (n_update - n_adjust)
    rng.shuffle(ops)
    ops = ["set"] + ops
    first_withdraw = ops.index("withdraw")
    first_update = next(i for i, op in enumerate(ops) if i > 0 and op in UPDATES)
    if first_withdraw < first_update:  # the first withdrawal needs an update to name
        ops[first_withdraw], ops[first_update] = ops[first_update], ops[first_withdraw]

    # Each record is withdrawn at most once; the first set never is.
    last_withdraw = max(i for i, op in enumerate(ops) if op == "withdraw")
    updates, withdrawals, nested_seen = [], [], False
    targets: list[int | None] = [None] * count
    for i, op in enumerate(ops):
        if op in UPDATES and i > 0:
            updates.append(i)
        elif op == "withdraw":
            nested = profile.nested_withdraw and bool(withdrawals) and (
                rng.random() < NESTED_SHARE or (i == last_withdraw and not nested_seen) or not updates
            )
            pool = withdrawals if nested else updates
            if not pool:
                return None
            # "latest" names the most recent record not yet named by a withdrawal.
            target = pool[-1] if profile.withdraw_target == "latest" else rng.choice(pool)
            pool.remove(target)
            targets[i] = target
            nested_seen = nested_seen or nested
            withdrawals.append(i)
    return list(zip(ops, targets))


def _attempt(rng: random.Random, n: int, profile: Profile, seed: int, names: list[str]) -> Chain | None:
    share = n // len(names)
    sizes = [n - share * (len(names) - 1)] + [share] * (len(names) - 1)  # names[0] is the question's project
    layouts = [_layout(rng, size, profile) for size in sizes]
    if any(layout is None for layout in layouts):
        return None
    order = [k for k, size in enumerate(sizes) for _ in range(size)]
    rng.shuffle(order)  # every project's first record is a set, so record #1 is always a set

    # Global ids, authors, dates. Withdrawals belong to their target's project.
    position = [0] * len(names)
    global_id: dict[tuple[int, int], int] = {}
    specs = []
    day = START_DAY
    for record_id, k in enumerate(order, 1):
        local = position[k]
        position[k] += 1
        global_id[(k, local)] = record_id
        op, target = layouts[k][local]
        if op == "note":
            author = rng.choice(OTHER_AUTHORS)
        elif op == "neutral":
            author = FINANCE if rng.random() < NEUTRAL_FINANCE_SHARE else rng.choice(OTHER_AUTHORS)
        else:
            author = FINANCE
        specs.append((record_id, k, op, None if target is None else global_id[(k, target)], author, day))
        day += timedelta(days=1 if rng.random() < 0.7 else 2)

    structure = [Record(rid, author, op, names[k], target=target) for rid, k, op, target, author, _ in specs]
    active = active_status(structure)

    # Amounts, walking forward so the true budget stays in range. Withdrawn updates and notes are
    # sized against the true budget too, so they look like the updates around them.
    true: dict[int, int | None] = dict.fromkeys(range(len(names)))
    records, before = [], {}
    for rid, k, op, target, author, _ in specs:
        amount, relative = None, False
        before[rid] = true[k]
        if op == "set":
            amount = rng.randrange(500, 2001, 10) if true[k] is None else _new_level(rng, true[k])
            if true[k] is None or active[rid]:
                true[k] = amount
        elif op == "adjust":
            amount = _change(rng, true[k])
            if active[rid]:
                true[k] += amount
        elif op == "note":
            relative = profile.relative_notes and rng.random() < RELATIVE_NOTE_SHARE
            amount = _change(rng, true[k]) if relative else _new_level(rng, true[k])
        records.append(Record(rid, author, op, names[k], amount, relative, target))

    by_id = {r.id: r for r in records}
    days = {rid: day for rid, *_, day in specs}
    width = max(3, len(str(n)))
    entries = []
    for r in records:
        text = _text(rng, r, by_id, days, before, profile, width)
        neutral = _neutral(rng, r)
        entries.append(Entry(r, days[r.id], text, neutral))
    return Chain(seed, n, profile, names[0], names, entries)


def _change(rng: random.Random, level: int) -> int:
    """A signed change of $5K to $150K that keeps the budget in range, pulled toward the middle."""
    size = rng.randrange(5, 155, 5)
    up = rng.random() < (0.8 if level < 700 else 0.2 if level > 2500 else 0.5)
    if not LOW <= level + (size if up else -size) <= HIGH:
        up = not up
    return size if up else -size


def _new_level(rng: random.Random, level: int) -> int:
    """A new budget figure within -30% / +40% of the current one, at least $20K away."""
    while True:
        new = min(max(round(level * rng.uniform(0.7, 1.4) / 10) * 10, LOW + 100), HIGH - 200)
        if abs(new - level) >= 20:
            return new


def _text(rng, r: Record, by_id: dict[int, Record], days: dict[int, date], before: dict[int, int | None], profile: Profile, width: int) -> str:
    if r.op == "set":
        return rng.choice(SET).format(p=r.entity, v=r.amount)
    if r.op == "adjust":
        template, up, down = rng.choice(ADJUST)
        return template.format(p=r.entity, d=up if r.amount > 0 else down, v=abs(r.amount))
    if r.op == "withdraw":
        phrasing = rng.randrange(2)  # drawn for both styles so P0 and P1 share chains
        if profile.withdraw_ref == "id":
            return WITHDRAW_ID[phrasing].format(t=f"{r.target:0{width}d}")
        target = by_id[r.target]
        kind = {"set": "budget setting", "withdraw": "withdrawal"}.get(target.op)
        kind = kind or ("increase" if target.amount > 0 else "decrease")
        return WITHDRAW_DESCRIPTION[phrasing].format(t=f"{days[target.id].isoformat()} {kind}")
    if r.op == "note":
        template, up, down = rng.choice(NOTE_RELATIVE if r.relative else NOTE_ABSOLUTE)
        rises = r.amount > 0 if r.relative else r.amount > before[r.id]
        return template.format(p=r.entity, d=up if rises else down, v=abs(r.amount))
    return _neutral(rng, r)


def _neutral(rng: random.Random, r: Record) -> str:
    template = rng.choice(NEUTRAL_FINANCE if r.author == FINANCE else NEUTRAL)
    return template.format(
        p=r.entity,
        n=rng.randint(2, 9),
        room=f"{rng.randint(1, 6)}{rng.choice('ABCD')}",
        day=rng.choice(WEEKDAYS),
        week=rng.randint(2, 48),
        code=f"FC-{rng.randint(1000, 9999)}",
    )
