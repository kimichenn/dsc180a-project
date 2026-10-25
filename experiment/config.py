"""Run configs (config/*.toml): what a run generates, which models it calls, and its design.

`prepare` copies the parsed config into the run's manifest, and every later command reads it
from there. Editing a config file never changes a run that already exists.
"""

from __future__ import annotations

import random
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path

from experiment.records import VERSIONS

PROVIDERS = ("claude-code", "codex")
# main: the study's evidence, prepared once from committed code. development: trials that check the
# setup; their logs are never analyzed as evidence or pooled with the main run.
PURPOSES = ("main", "development")


@dataclass(frozen=True)
class GeneratorSettings:
    records: int = 1600
    # Shares of the log. The opening budget counts toward adjust_share; filler gets what is left.
    adjust_share: float = 0.45
    withdraw_share: float = 0.15
    gossip_share: float = 0.30
    nested_rate: float = 0.35  # chance a withdrawal names an earlier withdrawal, when one is free
    relative_gossip_share: float = 0.5  # share of gossip that states a change rather than a figure
    # Change sizes in $K. Regular changes are multiples of amount_step up to amount_max. Every change
    # a withdrawal touches and every relative gossip claim gets its own size instead: one that is not
    # a multiple of amount_step, drawn from 1..unique_amount_max, and used by no other record.
    amount_step: int = 5
    amount_max: int = 150
    unique_amount_max: int = 600
    budget_min: int = 200  # every version's running budget stays in this range at every step ($K)
    budget_max: int = 5000

    def __post_init__(self):
        shares = (self.adjust_share, self.withdraw_share, self.gossip_share)
        if any(s < 0 for s in shares) or sum(shares) > 1:
            raise ValueError("generator shares must be non-negative and sum to at most 1")
        if not 0 <= self.nested_rate <= 1 or not 0 <= self.relative_gossip_share <= 1:
            raise ValueError("nested_rate and relative_gossip_share must be between 0 and 1")
        if self.amount_step < 2 or self.amount_max < self.amount_step or self.amount_max % self.amount_step:
            raise ValueError("amount_max must be a multiple of amount_step, which must be at least 2")
        if self.budget_max - self.budget_min < 2 * max(self.amount_max, self.unique_amount_max):
            raise ValueError("the budget range must be at least twice as wide as the largest change")


@dataclass(frozen=True)
class ModelSpec:
    name: str  # alias used in trial ids and results, e.g. "claude"
    provider: str  # claude-code | codex
    model: str  # the id the CLI takes
    effort: str  # reasoning effort the CLI takes
    # Claude Code enforces it; Codex cannot, so both are flagged hit_length_limit by the same rule.
    max_output_tokens: int = 32000

    def __post_init__(self):
        if self.provider not in PROVIDERS:
            raise ValueError(f"model {self.name}: provider must be one of {', '.join(PROVIDERS)}")


@dataclass(frozen=True)
class Tier:
    """Some logs, each with every version x instruction cell repeated `repeats` times."""

    logs: int
    versions: tuple[str, ...]
    instructions: tuple[str, ...]
    repeats: int

    def __post_init__(self):
        if self.logs < 1 or self.repeats < 1:
            raise ValueError("a tier needs at least one log and one repeat")
        unknown = set(self.versions) - set(VERSIONS)
        if unknown or not self.versions or len(set(self.versions)) != len(self.versions):
            raise ValueError(f"versions must be distinct values from {', '.join(VERSIONS)}")
        if not self.instructions or len(set(self.instructions)) != len(self.instructions):
            raise ValueError("instructions must be distinct and not empty")


@dataclass(frozen=True)
class RunConfig:
    description: str
    purpose: str  # one of PURPOSES
    seed_start: int
    schedule_seed: int
    selection_seed: int  # picks which logs get tier 2
    tier1: Tier  # every log
    # Some of tier 1's logs, cells, and instructions again, up to tier2.repeats in all: its repeats
    # continue tier 1's numbering, so it adds repeats tier1.repeats + 1 .. tier2.repeats.
    tier2: Tier
    timeout_seconds: int
    generator: GeneratorSettings
    models: dict[str, ModelSpec] = field(default_factory=dict)

    def __post_init__(self):
        if self.purpose not in PURPOSES:
            raise ValueError(f"purpose must be one of {', '.join(PURPOSES)}")
        if self.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive")
        t1, t2 = self.tier1, self.tier2
        if t2.logs > t1.logs or not set(t2.versions) <= set(t1.versions) or not set(t2.instructions) <= set(t1.instructions):
            raise ValueError("tier 2 must take its logs, versions, and instructions from tier 1")
        if t2.repeats <= t1.repeats:
            raise ValueError("tier 2's repeats count tier 1's, so it needs more of them")
        if not self.models:
            raise ValueError("a run needs at least one model")

    @property
    def seeds(self) -> range:
        return range(self.seed_start, self.seed_start + self.tier1.logs)

    @property
    def tier2_seeds(self) -> list[int]:
        """The logs that also get tier 2: a random draw, fixed by selection_seed."""
        return sorted(random.Random(self.selection_seed).sample(self.seeds, self.tier2.logs))


def load_config(path: Path) -> RunConfig:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    design = data["design"]
    return RunConfig(
        description=data.get("description", ""),
        purpose=data["purpose"],
        seed_start=design["seed_start"],
        schedule_seed=design["schedule_seed"],
        selection_seed=design["selection_seed"],
        tier1=_tier(design["tier1"]),
        tier2=_tier(design["tier2"]),
        timeout_seconds=data.get("collection", {}).get("timeout_seconds", 1800),
        generator=GeneratorSettings(**data.get("generator", {})),
        models={name: ModelSpec(name=name, **spec) for name, spec in data["models"].items()},
    )


def config_to_dict(config: RunConfig) -> dict:
    return asdict(config)


def config_from_dict(data: dict) -> RunConfig:
    nested = ("tier1", "tier2", "generator", "models")
    return RunConfig(
        **{k: v for k, v in data.items() if k not in nested},
        tier1=_tier(data["tier1"]),
        tier2=_tier(data["tier2"]),
        generator=GeneratorSettings(**data["generator"]),
        models={name: ModelSpec(**spec) for name, spec in data["models"].items()},
    )


def _tier(data: dict) -> Tier:
    return Tier(data["logs"], tuple(data["versions"]), tuple(data["instructions"]), data["repeats"])
