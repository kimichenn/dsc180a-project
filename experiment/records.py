"""One line of a budget log, and the versions of a log.

Every version has the same records at the same positions and the same answer. A version switches
some records off: their line becomes harmless filler from the same author.

    C   clean: no gossip, no withdrawals (withdrawals and the changes they cancel are filler)
    R   withdrawals
    RG  withdrawals and gossip (the full log)
    E   R with every withdrawal rewritten as the plain Finance change it amounts to (explicit reversals)
"""

from __future__ import annotations

from dataclasses import dataclass

FINANCE = "Finance Office"
KINDS = ("opening", "adjust", "withdraw", "gossip", "filler")
OFFICIAL = ("opening", "adjust", "withdraw")  # only the Finance Office writes these
VERSIONS = ("C", "R", "RG", "E")
KEEPS_GOSSIP = ("RG",)
KEEPS_WITHDRAWALS = ("R", "RG", "E")  # E keeps them as explicit reversals


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
    reversal: int | None = None  # withdraw only: the signed change it makes, which E states outright
    reversal_text: str = ""  # withdraw only: E's line for that change
