"""Generate a v4 event log about N fictional projects, and its matched Consistent version.

The generator plans each project's records (an authoritative chain plus any traps), dates
them, and picks authors whose office on that date gives the record the intended standing.
The answer always comes from the resolver, never from the plan; checks.py confirms they agree.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from functools import cached_property

from eventlog.dials import Dials
from eventlog.resolver import Person, Policy, Record, resolve
from harness.names import codenames

YEAR = 2025
MEMO_DATE = date(YEAR, 9, 1)
RECORD_START = date(YEAR, 9, 2)
RECORD_DAYS = 60  # records are dated Sep 2 - Oct 31
LAUNCH_START, LAUNCH_END = date(YEAR, 11, 3), date(YEAR, 12, 19)

PROGRAM, OTHER_PROGRAM = "Atlas", "Helios"
PROGRAM_OFFICE, RELEASE_BOARD = "Program Office", "Release Board"
ENGINEERING, VENDORS = "Engineering", "Vendor Relations"
OTHER_OFFICE = f"{OTHER_PROGRAM} Program Office"

TRAP_TYPES = ("distractor", "superseded", "retracted", "pre_authority")
SOURCES = {"changelog": "DATABASE CHANGELOG", "email": "EMAIL EXPORT", "ticket": "TICKET EXPORT"}
SOURCE_WEIGHTS = {
    "counting": {"changelog": 0.6, "ticket": 0.25, "email": 0.15},
    "note": {"email": 0.6, "ticket": 0.4},
    "pre_authority": {"changelog": 0.35, "ticket": 0.45, "email": 0.2},
    "other": {"changelog": 0.4, "ticket": 0.4, "email": 0.2},
}

# Phrasings as (Conflict wording, Consistent wording) pairs of similar length. The Consistent
# wording states the project's governing value: corrections become confirmations, retractions
# become reconfirmations, notes agree.
SET = [("{p} launch set to {v}.",) * 2, ("Setting {p} launch date to {v}.",) * 2, ("{p} is scheduled to launch {v}.",) * 2]
CONFIRM = [("{p} launch confirmed for {v}.",) * 2, ("Confirming {p} launch date of {v}.",) * 2]
CORRECT = [
    ("{p} launch moved to {v}.", "{p} launch confirmed for {v}."),
    ("Changing {p} launch date to {v}.", "Confirming {p} launch date of {v}."),
    ("Updating {p} to {v} per vendor call.", "Keeping {p} at {v} per vendor call."),
    ("{p} now launches {v}.", "{p} still launches {v}."),
]
RETRACT = [
    ("Retracting the {d} change to {p}.", "Reconfirming {p} for {v} after review."),
    ("Withdrawing the {d} update to {p}; it was entered in error.", "Reaffirming {p} at {v}; the {d} entry was checked."),
    ("Please disregard the {d} change to {p}.", "Please keep {p} at {v} as confirmed."),
]
NOTE = [  # (disagreeing, agreeing); notes that are not traps agree in both versions
    ("Heads up, {p} is slipping to {v}.", "Heads up, {p} is on track for {v}."),
    ("Hearing that {p} will launch {v} instead.", "Hearing that {p} will launch {v} as planned."),
    ("Vendor says {p} now targets {v}.", "Vendor says {p} still targets {v}."),
    ("I think {p} moves to {v}, can someone confirm?", "I think {p} stays at {v}, can someone confirm?"),
]
TEMPLATES = {"set": SET, "confirm": CONFIRM, "correct": CORRECT, "retract": RETRACT, "note": NOTE}

FIRST_NAMES = (
    "Dana", "Marcus", "Priya", "Tom", "Alicia", "Ben", "Chloe", "Diego", "Elena", "Farah", "Gavin", "Hana",
    "Ivan", "Jade", "Kofi", "Leah", "Mateo", "Nina", "Omar", "Paula", "Quinn", "Rosa", "Sam", "Tara",
    "Umar", "Vera", "Wes", "Ximena", "Yusuf", "Zoe", "Arjun", "Bianca", "Caleb", "Dmitri", "Esme", "Felix",
)
LAST_NAMES = (
    "Ruiz", "Lee", "Shah", "Wu", "Okafor", "Novak", "Brooks", "Haddad", "Ivanova", "Jensen", "Kaur", "Lindqvist",
    "Moreau", "Nakamura", "Ortiz", "Petrov", "Quintero", "Rahman", "Silva", "Tanaka", "Ueda", "Varga", "Walsh",
    "Xu", "Yilmaz", "Zimmer", "Abbott", "Bauer", "Castillo", "Dubois", "Eriksen", "Fischer",
)
_SUFFIXES = ("ra", "on", "is", "ex", "a", "o", "en", "ia")


@dataclass
class Event:
    id: int
    date: date
    author: str
    kind: str  # set | correct | confirm | retract | note
    project: str
    value: date | None  # Conflict-version value; None for retractions
    source: str
    phrasing: int
    shuffle_key: float  # position within its source section when records are grouped
    target: int | None = None  # id of the retracted record
    trap: str | None = None  # trap type this record carries; harness-only, never rendered


@dataclass
class Project:
    name: str
    budget: float
    planned: date  # governing value the generator aimed for; the resolver decides the real one
    traps: list[tuple[str, date]]


@dataclass
class Log:
    seed: int
    dials: Dials
    policy: Policy
    people: list[Person]  # in directory order
    projects: list[Project]  # in roster order
    other_projects: list[str]
    events: list[Event]
    threshold: date
    budget_threshold: float | None

    @cached_property
    def people_by_name(self) -> dict[str, Person]:
        return {p.name: p for p in self.people}

    @cached_property
    def governing(self) -> dict[str, date]:
        """Each in-program project's launch date under the policy, from the Conflict records."""
        return self.resolved("conflict")

    def records(self, version: str) -> list[Record]:
        out = []
        for e in self.events:
            if version == "consistent" and e.project in self.governing:
                op, value, target = ("none" if e.kind == "note" else "assign"), self.governing[e.project], None
            else:
                op, value, target = {"note": "none", "retract": "retract"}.get(e.kind, "assign"), e.value, e.target
            out.append(Record(e.id, e.date, e.author, op, e.project, value, target))
        return out

    def resolved(self, version: str) -> dict[str, date]:
        projects = {p.name for p in self.projects}
        return resolve(self.records(version), self.policy, self.people_by_name, projects)

    @property
    def question(self) -> str:
        when = f"{self.threshold:%B} {self.threshold.day}"
        if self.budget_threshold is None:
            return f"Which {PROGRAM} projects launch before {when}?"
        return f"Which {PROGRAM} projects launch before {when} and have a budget above ${self.budget_threshold:.1f}M?"

    def included(self, project: Project) -> bool:
        on_time = self.governing[project.name] < self.threshold
        return on_time and (self.budget_threshold is None or project.budget > self.budget_threshold)

    @property
    def answer(self) -> list[str]:
        return sorted(p.name for p in self.projects if self.included(p))

    def render(self, version: str) -> str:
        by_id = {e.id: e for e in self.events}
        blocks = [self._memo()]
        if self.policy.handover is not None:
            blocks.append(self._policy_update())
        blocks += [self._directory(), self._roster()]
        if self.dials.record_order == "grouped":
            for source, title in SOURCES.items():
                section = sorted((e for e in self.events if e.source == source), key=lambda e: e.shuffle_key)
                blocks.append("\n".join([title] + [self._line(e, version, by_id, with_source=False) for e in section]))
        else:
            ordered = sorted(self.events, key=lambda e: (e.date, e.id))
            blocks.append("\n".join(["RECORDS"] + [self._line(e, version, by_id, with_source=True) for e in ordered]))
        return "\n\n".join(blocks)

    def metadata(self) -> dict:
        return {
            "seed": self.seed,
            "dials": asdict(self.dials),
            "question": self.question,
            "answer": self.answer,
            "threshold": self.threshold.isoformat(),
            "budget_threshold": self.budget_threshold,
            "projects": [
                {
                    "name": p.name,
                    "budget": p.budget,
                    "governing": self.governing[p.name].isoformat(),
                    "included": self.included(p),
                    "traps": [{"type": kind, "value": value.isoformat()} for kind, value in p.traps],
                }
                for p in self.projects
            ],
            "other_projects": self.other_projects,
        }

    def _memo(self) -> str:
        return (
            f"POLICY MEMO - {_short(MEMO_DATE)}\n"
            f"Launch dates for {PROGRAM} program projects are set by the {PROGRAM_OFFICE}. "
            f"Messages from {ENGINEERING} or {VENDORS} are informational and never change a launch date. "
            "A record counts only if its author's office held this authority on the date the record was issued. "
            "A later authorized record replaces earlier ones. "
            "A retraction restores the value that the retracted record replaced."
        )

    def _policy_update(self) -> str:
        return (
            f"POLICY UPDATE - {_short(self.policy.handover)}\n"
            f"Effective today, the {RELEASE_BOARD} sets {PROGRAM} launch dates in place of the {PROGRAM_OFFICE}. "
            f"Dates the {PROGRAM_OFFICE} set before today stay in effect until the {RELEASE_BOARD} changes them."
        )

    def _directory(self) -> str:
        lines = ["STAFF DIRECTORY"]
        for p in self.people:
            if p.move_date is None:
                lines.append(f"{p.name} - {p.office}")
            else:
                until = _short(p.move_date - timedelta(days=1))
                lines.append(f"{p.name} - {p.office} until {until}; {p.moves_to} from {_short(p.move_date)}")
        return "\n".join(lines)

    def _roster(self) -> str:
        lines = [f"{PROGRAM.upper()} PROJECT ROSTER"]
        for p in self.projects:
            lines.append(p.name if self.budget_threshold is None else f"{p.name} - budget ${p.budget:.1f}M")
        return "\n".join(lines)

    def _line(self, e: Event, version: str, by_id: dict[int, Event], with_source: bool) -> str:
        office = ""
        if self.dials.authority_statement == "named":
            office = f" ({self.people_by_name[e.author].office_on(e.date)})"
        source = f", {e.source}" if with_source else ""
        return f"{_short(e.date)}{source}, {e.author}{office}: {self._text(e, version, by_id)}"

    def _text(self, e: Event, version: str, by_id: dict[int, Event]) -> str:
        in_program = e.project in self.governing
        consistent = version == "consistent" and in_program
        value = self.governing[e.project] if consistent else e.value
        wordings = TEMPLATES[e.kind][e.phrasing]
        if e.kind == "note":
            wording = wordings[1 if consistent or (in_program and e.trap is None) else 0]
        else:
            wording = wordings[1 if consistent else 0]
        retracted = by_id[e.target].date if e.target is not None else None
        return wording.format(p=e.project, v=_short(value) if value else "", d=_short(retracted) if retracted else "")


def _short(day: date) -> str:
    return f"{day:%b} {day.day}"


@dataclass
class _Step:
    """One planned record for a project, before it has a date and author."""

    kind: str
    value: date | None
    counting: bool
    trap: str | None = None
    pool: str = "authority"  # authority | notes | early_board | mover
    before: date | None = None  # must be dated before this day
    retracts: int | None = None  # index of the retracted step
    same_era: bool = False  # a retracted correction and its retraction share an authority era


def generate(dials: Dials, seed: int) -> Log:
    rng = random.Random(f"eventlog-{seed}")
    policy, people, groups, mover = _staff(rng, dials)
    threshold = LAUNCH_START + timedelta(days=rng.randint(17, 29))
    budget_threshold = rng.choice((2.5, 3.0, 3.5)) if dials.two_conditions else None

    taken: set[str] = set()
    names = codenames(rng, dials.n_projects, taken)
    n_trapped = round(dials.trap_density * dials.n_projects)
    plans = _trap_plans(rng, dials, n_trapped) + [[] for _ in range(dials.n_projects - n_trapped)]
    on_time = [i % 2 == 0 for i in range(n_trapped)]  # trapped projects: half included, half excluded
    rng.shuffle(on_time)
    on_time += [rng.random() < 0.5 for _ in range(dials.n_projects - n_trapped)]

    specs = list(zip(names, plans, on_time))
    rng.shuffle(specs)
    events: list[Event] = []
    projects = []
    for name, plan, early in specs:
        project = _project(rng, name, plan, early, threshold, budget_threshold)
        projects.append(project)
        events += _project_events(rng, project, policy, people, groups, mover, start_id=len(events))

    other_projects = []
    if dials.out_of_program:
        program_count = len(events)
        while len(events) < 2 * program_count:
            other = _similar_name(rng, names, taken)
            other_projects.append(other)
            events += _other_events(rng, other, groups[OTHER_OFFICE], start_id=len(events))

    rng.shuffle(projects)
    rng.shuffle(people)
    return Log(seed, dials, policy, people, projects, other_projects, events, threshold, budget_threshold)


def available_trap_types(dials: Dials) -> list[str]:
    if dials.trap_types == "distractor":
        return ["distractor"]
    types = ["distractor", "superseded", "retracted"]
    if dials.authority_changes != "none":
        types.append("pre_authority")  # needs an office or person whose authority starts later
    return types


def single_trap_quota(dials: Dials) -> int:
    """At least 5 single-trap projects of each type, relaxed when there are too few trapped projects."""
    n_trapped = round(dials.trap_density * dials.n_projects)
    return min(5, n_trapped // len(available_trap_types(dials)))


def _trap_plans(rng: random.Random, dials: Dials, n_trapped: int) -> list[list[str]]:
    types = available_trap_types(dials)
    plans = [[kind] for kind in types for _ in range(single_trap_quota(dials))]
    while len(plans) < n_trapped:
        k = 1 if dials.max_traps == 1 else rng.randint(1, dials.max_traps)
        plans.append(rng.sample(types, k) if len(types) > 1 else types * k)
    rng.shuffle(plans)
    return plans


def _staff(rng: random.Random, dials: Dials):
    handover = mover_date = None
    if dials.authority_changes != "none":
        handover = RECORD_START + timedelta(days=rng.randint(23, 38))
        if dials.authority_changes == "handover+mover":
            mover_date = handover + timedelta(days=rng.randint(3, 6))
    policy = Policy(PROGRAM_OFFICE, RELEASE_BOARD if handover else None, handover)

    sizes = {PROGRAM_OFFICE: 4, ENGINEERING: 4, VENDORS: 3}
    if handover:
        sizes[RELEASE_BOARD] = 4
    if dials.out_of_program:
        sizes[OTHER_OFFICE] = 4
    # No two people share a first or a last name, so authority lookups are never confusable.
    count = sum(sizes.values()) + 1
    chosen = iter(f"{first} {last}" for first, last in zip(rng.sample(FIRST_NAMES, count), rng.sample(LAST_NAMES, count)))
    groups = {office: [Person(next(chosen), office) for _ in range(size)] for office, size in sizes.items()}
    groups["notes"] = groups[ENGINEERING] + groups[VENDORS]
    people = [p for office in sizes for p in groups[office]]
    mover = None
    if mover_date:
        mover = Person(next(chosen), ENGINEERING, RELEASE_BOARD, mover_date)
        people.append(mover)
    return policy, people, groups, mover


def _project(rng, name, plan, early, threshold, budget_threshold) -> Project:
    day = timedelta(days=1)
    near, far = (LAUNCH_START, threshold - day), (threshold + day, LAUNCH_END)
    governing_range, trap_range = (near, far) if early else (far, near)
    planned = _day_in(rng, *governing_range)
    trap_days = rng.sample(range((trap_range[1] - trap_range[0]).days + 1), len(plan))
    traps = [(kind, trap_range[0] + timedelta(days=offset)) for kind, offset in zip(plan, trap_days)]
    if budget_threshold is not None and (plan or rng.random() < 0.5):
        budget = round(rng.uniform(budget_threshold + 0.1, 6.0), 1)  # trapped projects always meet the budget
    else:
        budget = round(rng.uniform(1.0, (budget_threshold or 6.0) - 0.1), 1)
    return Project(name, budget, planned, traps)


def _project_steps(rng, project: Project, policy: Policy, mover: Person | None) -> list[_Step]:
    traps = dict(project.traps)  # only distractor notes can repeat, and they are read from project.traps below
    steps: list[_Step] = []
    if "superseded" in traps:
        steps += [_Step("set", traps["superseded"], True, trap="superseded"), _Step("correct", project.planned, True)]
    else:
        steps.append(_Step("set", project.planned, True))
    if "retracted" in traps:
        index = len(steps)
        steps.append(_Step("correct", traps["retracted"], True, trap="retracted", same_era=True))
        steps.append(_Step("retract", None, True, retracts=index, same_era=True))
    if not project.traps:  # clean project: optional confirmation and agreeing note
        if rng.random() < 0.3:
            steps.append(_Step("confirm", project.planned, True))
        if rng.random() < 0.3:
            steps.append(_Step("note", project.planned, False, pool="notes"))

    # Non-counting traps come after the last counting record, so believing one changes the answer.
    late = []
    for kind, value in project.traps:
        if kind == "distractor":
            late.append(_Step("note", value, False, trap="distractor", pool="notes"))
        elif kind == "pre_authority":
            use_mover = mover is not None and rng.random() < 0.5
            before = mover.move_date if use_mover else policy.handover
            late.append(_Step("correct", value, False, trap="pre_authority", pool="mover" if use_mover else "early_board", before=before))
    late.sort(key=lambda s: s.before is None)  # date-bounded steps first
    return steps + late


def _project_events(rng, project, policy, people, groups, mover, start_id) -> list[Event]:
    steps = _project_steps(rng, project, policy, mover)
    days = _sample_days(rng, steps, policy)
    events = []
    for i, (step, day) in enumerate(zip(steps, days)):
        role = "counting" if step.counting else ("pre_authority" if step.trap == "pre_authority" else "note")
        events.append(
            Event(
                id=start_id + i,
                date=day,
                author=_author(rng, step, day, policy, people, groups, mover),
                kind=step.kind,
                project=project.name,
                value=step.value,
                source=_weighted(rng, SOURCE_WEIGHTS[role]),
                phrasing=rng.randrange(len(TEMPLATES[step.kind])),
                shuffle_key=rng.random(),
                target=start_id + step.retracts if step.retracts is not None else None,
                trap=step.trap,
            )
        )
    return events


def _sample_days(rng, steps: list[_Step], policy: Policy) -> list[date]:
    """Distinct increasing dates that respect each step's bound and the same-era rule."""
    bounded = [i for i, s in enumerate(steps) if s.before is not None]
    for _ in range(10_000):
        if bounded:
            limit = min((steps[i].before - RECORD_START).days for i in bounded)
            head_n = bounded[-1] + 1
            if limit < head_n:
                break
            head = sorted(rng.sample(range(limit), head_n))
            rest_n = len(steps) - head_n
            if RECORD_DAYS - head[-1] - 1 < rest_n:
                continue
            offsets = head + sorted(rng.sample(range(head[-1] + 1, RECORD_DAYS), rest_n))
        else:
            offsets = sorted(rng.sample(range(RECORD_DAYS), len(steps)))
        days = [RECORD_START + timedelta(days=o) for o in offsets]
        eras = {policy.authority_on(d) for s, d in zip(steps, days) if s.same_era}
        if len(eras) <= 1:
            return days
    raise RuntimeError(f"could not date steps {[s.kind for s in steps]}")


def _author(rng, step: _Step, day: date, policy, people, groups, mover) -> str:
    if step.pool == "authority":
        office = policy.authority_on(day)
        pool = [p for p in people if p.office_on(day) == office]
    elif step.pool == "early_board":
        pool = groups[RELEASE_BOARD]
    elif step.pool == "mover":
        pool = [mover]
    else:
        pool = groups["notes"]
    return rng.choice(pool).name


def _other_events(rng, name: str, staff: list[Person], start_id: int) -> list[Event]:
    count = rng.randint(1, 3)
    days = sorted(rng.sample(range(RECORD_DAYS), count))
    kinds = ["set"] + [rng.choice(("correct", "confirm", "note")) for _ in range(count - 1)]
    return [
        Event(
            id=start_id + i,
            date=RECORD_START + timedelta(days=offset),
            author=rng.choice(staff).name,
            kind=kind,
            project=name,
            value=_day_in(rng, LAUNCH_START, LAUNCH_END),
            source=_weighted(rng, SOURCE_WEIGHTS["other"]),
            phrasing=rng.randrange(len(TEMPLATES[kind])),
            shuffle_key=rng.random(),
        )
        for i, (kind, offset) in enumerate(zip(kinds, days))
    ]


def _similar_name(rng, names: list[str], taken: set[str]) -> str:
    while True:
        name = rng.choice(names) + rng.choice(_SUFFIXES)
        if name.lower() not in taken:
            taken.add(name.lower())
            return name


def _day_in(rng, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def _weighted(rng, weights: dict[str, float]) -> str:
    return rng.choices(list(weights), weights=list(weights.values()))[0]
