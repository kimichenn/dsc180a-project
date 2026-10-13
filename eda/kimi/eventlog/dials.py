"""Difficulty dials and the stage plans from the v4 protocol."""

from __future__ import annotations

from dataclasses import dataclass, fields, replace


@dataclass(frozen=True)
class Dials:
    """Every dial starts at its maximum (the defaults)."""

    # General dials: make both versions harder.
    n_projects: int = 100
    out_of_program: bool = True
    two_conditions: bool = True
    # Conflict dials: only matter when records disagree.
    trap_density: float = 0.6
    max_traps: int = 3
    trap_types: str = "all"  # all | distractor
    authority_changes: str = "handover+mover"  # handover+mover | handover | none
    authority_statement: str = "inferred"  # inferred | named
    record_order: str = "grouped"  # grouped | chronological


CONFLICT_DIALS = ("trap_density", "max_traps", "trap_types", "authority_changes", "authority_statement", "record_order")
LOWEST = {
    "trap_density": 0.1,
    "max_traps": 1,
    "trap_types": "distractor",
    "authority_changes": "none",
    "authority_statement": "named",
    "record_order": "chronological",
}
N_LEVELS = (100, 50, 20, 5)

# Stage A rule 2: lower the general dials one step at a time, in this order.
STAGE_A_STEPS = (
    {},
    {"out_of_program": False},
    {"out_of_program": False, "two_conditions": False},
    {"out_of_program": False, "two_conditions": False, "n_projects": 50},
    {"out_of_program": False, "two_conditions": False, "n_projects": 20},
    {"out_of_program": False, "two_conditions": False, "n_projects": 5},
)

# Fresh logs are the unit of replication. Stage C seeds are never used before Stage C.
SEEDS = {"A": (1, 2, 3), "B": (101, 102, 103), "C": (1001, 1002, 1003, 1004, 1005, 1006)}


def dials_for(step: int, overrides: dict | None = None) -> Dials:
    return replace(Dials(), **STAGE_A_STEPS[step], **(overrides or {}))


def parse_overrides(items: list[str]) -> dict:
    """['n_projects=200', 'trap_types=distractor'] -> typed dial overrides."""
    types = {f.name: f.type for f in fields(Dials)}
    overrides = {}
    for item in items:
        key, _, raw = item.partition("=")
        if key not in types or not raw:
            raise ValueError(f"bad --set {item!r}; dials are {', '.join(types)}")
        kind = types[key]
        if kind == "bool":
            overrides[key] = raw.lower() in ("1", "true", "yes", "on")
        elif kind == "int":
            overrides[key] = int(raw)
        elif kind == "float":
            overrides[key] = float(raw)
        else:
            overrides[key] = raw
    return overrides


@dataclass(frozen=True)
class Setting:
    label: str
    dials: Dials
    versions: tuple[str, ...]


def stage_settings(stage: str, base: Dials) -> list[Setting]:
    """The log settings a stage runs, per the protocol."""
    both = ("consistent", "conflict")
    if stage in ("A", "C"):
        return [Setting("main", base, both)]
    # Stage B: N sweep (both versions) plus one-at-a-time conflict ablation (Conflict only;
    # Consistent logs do not depend on conflict dials, so the N sweep supplies the baseline).
    levels = [base.n_projects] + [n for n in N_LEVELS if n < base.n_projects]
    sweep = [Setting(f"n{n}", replace(base, n_projects=n), both) for n in levels]
    ablation = [Setting(f"ablate-{dial}", replace(base, **{dial: LOWEST[dial]}), ("conflict",)) for dial in CONFLICT_DIALS]
    return sweep + ablation
