"""One line of a budget log, and the four versions of a log.

Every version has the same records at the same positions. A version switches some records off:
their line becomes harmless filler from the same author, so all four versions have the same
length and the same answer.

    C   clean: no gossip, no withdrawals
    G   gossip only
    R   withdrawals only
    RG  gossip and withdrawals (the full log)
"""

from __future__ import annotations

from dataclasses import dataclass

FINANCE = "Finance Office"
KINDS = ("opening", "adjust", "withdraw", "gossip", "filler")
OFFICIAL = ("opening", "adjust", "withdraw")  # only the Finance Office writes these
VERSIONS = ("C", "G", "R", "RG")


@dataclass(frozen=True)
class Record:
    id: int
    kind: str  # opening | adjust | withdraw | gossip | filler
    author: str
    amount: int | None = None  # opening: starting budget; adjust: signed change; gossip: claimed budget or change ($K)
    target: int | None = None  # withdraw: id of the record it withdraws
    relative: bool = False  # gossip only: amount is a claimed change ("goes up $40K"), not a budget
    text: str = ""  # what the line says after "Author: "
    filler: str = ""  # what it says instead when a version switches the record off


def has_gossip(version: str) -> bool:
    return "G" in version


def has_withdrawals(version: str) -> bool:
    return "R" in version
