"""Everything the model reads: the policy, each record's wording, project names, and the rendered log.

The wording is Kimi's v5 (POLICY, templates, filler). parse_lines reads a rendered log back using
only what the policy says decides a record (its author and wording), so checks can confirm the
text says what the generator meant.
"""

from __future__ import annotations

import random
import re

from experiment.records import FINANCE, Record

POLICY = (
    "POLICY\n"
    "Only the Finance Office can change the budget. Messages from anyone else do not change it.\n"
    "The Finance Office can withdraw one of its earlier updates. A withdrawn update counts as if it never happened; "
    "every other update still applies, in order. A withdrawal can itself be withdrawn."
)
OTHER_AUTHORS = (
    "Engineering email", "PMO note", "Vendor call", "Operations chat",
    "Legal email", "Sales update", "Facilities ticket", "Marketing email",
)
OPENING = ("{p} budget set to ${v}K.", "{p} budget set to ${v}K after review.", "{p} budget set to ${v}K per the revised plan.")
ADJUST = ("{p} budget {d} by ${v}K.", "{p} budget {d} by ${v}K after review.", "{p} budget {d} by ${v}K per the revised plan.")
WITHDRAW = ("Withdraw update #{t}.", "Withdraw update #{t}; it was entered in error.")
# Gossip states a budget figure (direction words, when a template has them, compare it to the true
# budget) or a change ("goes up $40K"). Half of it is each, as in v5.
GOSSIP_CLAIM = (
    ("{p} budget is going {d} to ${v}K.", "up", "down"),
    ("{p} budget is going to ${v}K.", "", ""),
    ("Heard {p}'s budget is now ${v}K.", "", ""),
    ("{p} budget should land at ${v}K.", "", ""),
    ("Pretty sure {p}'s budget is ${v}K now.", "", ""),
)
GOSSIP_CHANGE = (
    ("Hearing {p}'s budget goes {d} ${v}K.", "up", "down"),
    ("{p} budget is going {d} by ${v}K.", "up", "down"),
    ("Expect {p}'s budget to {d} by ${v}K.", "rise", "drop"),
    ("Sounds like {p} gets ${v}K {d}.", "more", "less"),
)
# Filler: no dollar figures, and none of the words the budget records use.
FILLER = (
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
FILLER_FINANCE = (
    "{p} invoice batch {code} archived.",
    "{p} quarterly audit scheduled for {day}.",
    "{p} cost center code changed to {code}.",
    "Reminder: {p} expense reports are due {day}.",
    "{p} purchase order {code} closed.",
    "{p} finance review moved to Room {room}.",
    "{p} audit notes filed.",  # short ones stand in for short withdrawal lines
    "{p} receipts scanned.",
)
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")

# Made-up project names: two or three consonant-vowel syllables plus an optional ending (Kavel, Drumo).
_ONSETS = ("b", "d", "f", "g", "k", "l", "m", "n", "p", "r", "s", "t", "v", "z", "br", "dr", "kr", "tr", "st", "th")
_VOWELS = ("a", "e", "i", "o", "u")
_CODAS = ("", "", "", "n", "r", "l", "s", "x")


def _vocabulary() -> set[str]:
    texts = [POLICY, FINANCE, *OTHER_AUTHORS, *OPENING, *ADJUST, *WITHDRAW, *FILLER, *FILLER_FINANCE, *WEEKDAYS]
    texts += [" ".join(t) for t in GOSSIP_CLAIM + GOSSIP_CHANGE] + ["increased decreased question records"]
    return set(re.findall(r"[a-z]+", " ".join(texts).lower()))


VOCABULARY = _vocabulary()


def project_name(rng: random.Random) -> str:
    """A made-up name of at most 8 letters that is not a word the log's wording uses."""
    while True:
        syllables = "".join(rng.choice(_ONSETS) + rng.choice(_VOWELS) for _ in range(rng.choice((2, 2, 3))))
        name = syllables + rng.choice(_CODAS)
        if len(name) <= 8 and name not in VOCABULARY:
            return name.capitalize()


def id_width(n: int) -> int:
    return max(3, len(str(n)))


def opening(rng: random.Random, project: str, amount: int) -> str:
    return rng.choice(OPENING).format(p=project, v=amount)


def adjust(rng: random.Random, project: str, amount: int) -> str:
    return rng.choice(ADJUST).format(p=project, d="increased" if amount > 0 else "decreased", v=abs(amount))


def withdraw(rng: random.Random, target: int, width: int) -> str:
    return rng.choice(WITHDRAW).format(t=f"{target:0{width}d}")


def reversal(project: str, amount: int, line: str) -> str:
    """E's line for what a withdrawal does: a plain Finance change in the wording closest in length
    to the withdrawal line it replaces, so E stays the same length as R."""
    options = [template.format(p=project, d="increased" if amount > 0 else "decreased", v=abs(amount)) for template in ADJUST]
    return min(options, key=lambda option: abs(len(option) - len(line)))


def gossip_claim(rng: random.Random, project: str, claim: int, budget: int) -> str:
    template, up, down = rng.choice(GOSSIP_CLAIM)
    return template.format(p=project, d=up if claim > budget else down, v=claim)


def gossip_change(rng: random.Random, project: str, change: int) -> str:
    template, up, down = rng.choice(GOSSIP_CHANGE)
    return template.format(p=project, d=up if change > 0 else down, v=abs(change))


def filler(rng: random.Random, project: str, author: str) -> str:
    template = rng.choice(FILLER_FINANCE if author == FINANCE else FILLER)
    return template.format(
        p=project,
        n=rng.randint(2, 9),
        room=f"{rng.randint(1, 6)}{rng.choice('ABCD')}",
        day=rng.choice(WEEKDAYS),
        week=rng.randint(2, 48),
        code=f"FC-{rng.randint(1000, 9999)}",
    )


def filler_like(rng: random.Random, project: str, author: str, line: str, draws: int = 4) -> str:
    """Filler to stand in for `line`: of a few drawn, the closest in length, so versions stay the same length."""
    return min((filler(rng, project, author) for _ in range(draws)), key=lambda option: abs(len(option) - len(line)))


def question(project: str) -> str:
    return f"What is {project}'s budget now?"


def record_lines(records: list[Record]) -> list[str]:
    width = id_width(len(records))
    return [f"#{r.id:0{width}d}  {r.author}: {r.text}" for r in records]


def render_log(records: list[Record]) -> str:
    return f"{POLICY}\n\nRECORDS\n" + "\n".join(record_lines(records))


LINE = re.compile(r"^#(\d+)\s+(.+?):\s+(.*)$")
OPENING_TEXT = re.compile(r"\bbudget set to \$(\d+)K\b")
ADJUST_TEXT = re.compile(r"\bbudget (increased|decreased) by \$(\d+)K\b")
WITHDRAW_TEXT = re.compile(r"^Withdraw update #(\d+)\b")
CLAIM_TEXT = re.compile(r"\$(\d+)K")


def parse_log(text: str) -> list[Record]:
    """Records read back from a rendered log (or a whole prompt): the lines after RECORDS, up to the first blank line."""
    _, found, body = text.partition("RECORDS\n")
    if not found:
        raise ValueError("no RECORDS section")
    return parse_lines(body.split("\n\n")[0].splitlines())


def parse_lines(lines: list[str]) -> list[Record]:
    """Official records keep their amount and target. Gossip keeps the first figure it names, without
    telling a claimed budget from a claimed change: what gossip says never changes the answer."""
    records = []
    for line in lines:
        m = LINE.match(line.strip())
        if not m:
            raise ValueError(f"unreadable record line {line!r}")
        rid, author, body = int(m[1]), m[2], m[3]
        if author == FINANCE:
            if w := WITHDRAW_TEXT.match(body):
                record = Record(rid, "withdraw", author, target=int(w[1]), text=body)
            elif s := OPENING_TEXT.search(body):
                record = Record(rid, "opening", author, amount=int(s[1]), text=body)
            elif a := ADJUST_TEXT.search(body):
                record = Record(rid, "adjust", author, amount=int(a[2]) * (1 if a[1] == "increased" else -1), text=body)
            elif re.search(r"\$|budget|withdraw", body, re.IGNORECASE):
                raise ValueError(f"#{rid}: Finance Office line matches no update pattern: {body!r}")
            else:
                record = Record(rid, "filler", author, text=body)
        elif c := CLAIM_TEXT.search(body):
            record = Record(rid, "gossip", author, amount=int(c[1]), text=body)
        else:
            record = Record(rid, "filler", author, text=body)
        records.append(record)
    return records
