"""The v5 profile (every setting except N) and the phase plans."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Profile:
    note_rate: float = 0.30  # share of records that are notes
    withdraw_rate: float = 0.15  # share that are withdrawals
    nested_withdraw: bool = True  # withdrawals may target withdrawals
    withdraw_target: str = "any"  # any | latest
    # Share of counting updates after #001 that are adjust (vs set). An active set erases every
    # earlier record's effect, so at 0.80 the answer depends on only the last ~7 records at any N
    # and no attempt meets the generator guarantees at N >= 200. At 1.0 only #001 is a set.
    relative_rate: float = 1.0
    relative_notes: bool = True  # notes may be relative
    withdraw_ref: str = "id"  # id | description ("Withdraw the 2025-09-05 increase.")
    n_entities: int = 1  # >1 interleaves other projects' chains; question asks about one
    response_format: str = "working"  # working | final_only
    neutral_rate: float = 0.10


# Escalation, used only if a flagship survives the current profile at max N. Each adds one change.
PROFILES = {"P0": Profile()}
PROFILES["P1"] = replace(PROFILES["P0"], withdraw_ref="description")
PROFILES["P2"] = replace(PROFILES["P1"], n_entities=5)
PROFILES["P3"] = replace(PROFILES["P2"], response_format="final_only")
ESCALATION = tuple(PROFILES)

BREAK_LEVELS = (20, 50, 100, 200, 400, 800)
BREAK_SEEDS = (1, 2, 3, 4, 5)
# Fresh chains are the unit of replication. Sweep seeds start here and never reuse break seeds.
SWEEP_SEED_START = 1001
SWEEP_SEEDS = 30
