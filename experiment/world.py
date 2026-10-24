"""A generated log (a "world"): its records, its versions, and its answer key."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, replace
from functools import cached_property

from experiment import scoring, solvers, text
from experiment.records import KEEPS_GOSSIP, KEEPS_WITHDRAWALS, VERSIONS, Record


@dataclass
class World:
    world_id: str
    seed: int
    project: str
    records: list[Record]  # the full log, version RG
    attempts: int = 1  # generator attempts before every check passed

    @property
    def n(self) -> int:
        return len(self.records)

    @cached_property
    def active(self) -> dict[int, bool]:
        return solvers.active_status(self.records)

    @cached_property
    def answer(self) -> int:
        return solvers.solve_backward(self.records)

    @cached_property
    def chains(self) -> list[solvers.Chain]:
        return solvers.chains(self.records)

    def switched_off(self, record: Record, version: str) -> bool:
        """Gossip is off unless the version keeps gossip. Withdrawals and the adjustments they cancel
        are off unless it keeps withdrawals; adjustments that end up active stay, so the answer holds."""
        if record.kind == "gossip":
            return version not in KEEPS_GOSSIP
        if record.kind == "withdraw" or (record.kind == "adjust" and not self.active[record.id]):
            return version not in KEEPS_WITHDRAWALS
        return False

    def version(self, version: str) -> list[Record]:
        if version not in VERSIONS:
            raise ValueError(f"unknown version {version!r}")
        records = []
        for r in self.records:
            if self.switched_off(r, version):
                r = replace(r, kind="filler", amount=None, target=None, relative=False, text=r.filler)
            elif version == "E" and r.kind == "withdraw":
                r = replace(r, kind="adjust", amount=r.reversal, target=None, text=r.reversal_text)
            records.append(r)
        return records

    def render(self, version: str) -> str:
        return text.render_log(self.version(version))

    @cached_property
    def key(self) -> dict:
        """The answer key scoring uses. Buckets come from each record's role in the full log, so a
        mistake on a record lands in the same bucket in every version."""
        return {
            "answer": self.answer,
            "buckets": scoring.mistake_values(self.records),
            "chains": [{**asdict(c), "depth": c.depth} for c in self.chains],
        }

    def diagnostics(self) -> dict:
        chars = {v: len(self.render(v)) for v in VERSIONS}
        return {
            "kinds": dict(Counter(r.kind for r in self.records)),
            "relative_gossip": sum(1 for r in self.records if r.kind == "gossip" and r.relative),
            "surviving_adjustments": sum(1 for r in self.records if r.kind == "adjust" and self.active[r.id]),
            "chains": len(self.chains),
            "nested_chains": sum(1 for c in self.chains if c.depth > 1),
            "max_chain_depth": max((c.depth for c in self.chains), default=0),
            "chars": chars,
            "length_vs_C": {v: round(chars[v] / chars["C"] - 1, 4) for v in VERSIONS},
        }

    def to_json(self) -> dict:
        return {
            "world_id": self.world_id,
            "seed": self.seed,
            "project": self.project,
            "question": text.question(self.project),
            "attempts": self.attempts,
            **self.key,
            "diagnostics": self.diagnostics(),
            "records": [asdict(r) for r in self.records],
        }

    @classmethod
    def from_json(cls, data: dict) -> World:
        records = [Record(**r) for r in data["records"]]
        return cls(data["world_id"], data["seed"], data["project"], records, data.get("attempts", 1))
