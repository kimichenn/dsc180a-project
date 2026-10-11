"""Stage presets from the protocol, and expansion of a design into a shuffled list of trials."""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, replace
from itertools import product

from conflict_eval.prompts import (
    DISTANCES,
    DOC_ORDERS,
    INSTRUCTION_LEVELS,
    RULE_PLACEMENTS,
    VARIANTS,
    Condition,
)
from conflict_eval.scenarios import QUESTION_TYPES, Scenario


@dataclass(frozen=True)
class Design:
    stage: str
    questions: tuple[str, ...]
    distances: tuple[str, ...]
    rule_placements: tuple[str, ...]
    instructions: tuple[str, ...]
    generations: int
    rung: int = 0
    variants: tuple[str, ...] = VARIANTS


# Stage 1 as written (12 x 2 x 3 x 2 x 3 models = 432) holds rule placement fixed;
# pass --rule start near to vary it as well. Stage 2 has no default setting: it is
# chosen from the Stage 1 results.
STAGES = {
    "stage0": Design("stage0", ("two_step",), ("far",), ("start",), ("none",), generations=3),
    "stage1": Design("stage1", QUESTION_TYPES, DISTANCES, ("start",), ("none",), generations=1),
    "stage2": Design("stage2", (), (), ("start",), INSTRUCTION_LEVELS, generations=2),
}


def make_design(stage: str, rung: int, **overrides) -> Design:
    """A stage preset with the rung and any non-empty overrides applied."""
    design = replace(STAGES[stage], rung=rung, **{k: v for k, v in overrides.items() if v})
    if not design.questions or not design.distances:
        raise ValueError(f"{stage} needs an explicit --question and --distance (the setting chosen from Stage 1)")
    return design


@dataclass(frozen=True)
class Trial:
    scenario: Scenario
    model: str
    condition: Condition
    generation: int

    @property
    def id(self) -> str:
        c = self.condition
        parts = [self.scenario.id, self.model, c.variant, c.question_type, c.distance, c.rule_placement, c.instruction]
        return "|".join(parts + [f"rung{c.rung}", f"gen{self.generation}"])

    def record(self) -> dict:
        s = self.scenario
        return {
            "trial_id": self.id,
            "scenario_id": s.id,
            "domain": s.domain,
            "format": s.format,
            "conflict_subtype": s.conflict_subtype,
            "model": self.model,
            **asdict(self.condition),
            "generation": self.generation,
        }


def build_trials(design: Design, scenarios: list[Scenario], models: list[str], seed: int = 0) -> list[Trial]:
    """Every scenario x condition x model x generation, shuffled so conditions interleave."""
    multidoc_position = {s.id: i for i, s in enumerate(s for s in scenarios if s.format == "multi_document")}
    trials = []
    for scenario in scenarios:
        for cell in product(design.questions, design.distances, design.rule_placements, design.instructions):
            order = doc_order(multidoc_position.get(scenario.id), cell)
            for variant in design.variants:
                condition = Condition(variant, *cell, rung=design.rung, doc_order=order)
                for model in models:
                    for generation in range(1, design.generations + 1):
                        trials.append(Trial(scenario, model, condition, generation))
    random.Random(seed).shuffle(trials)
    return trials


def doc_order(multidoc_position: int | None, cell: tuple[str, str, str, str]) -> str:
    """Counterbalanced document order for one scenario cell.

    Alternates across multi-document scenarios and across cells within a scenario. The
    order never depends on variant, model, or generation, so matched Consistent/Conflict
    prompts are identical apart from the claim and every model sees the same prompt.
    """
    if multidoc_position is None:
        return "forward"  # multi-turn context stays chronological
    question, distance, placement, instruction = cell
    index = (
        multidoc_position
        + QUESTION_TYPES.index(question)
        + DISTANCES.index(distance)
        + RULE_PLACEMENTS.index(placement)
        + INSTRUCTION_LEVELS.index(instruction)
    )
    return DOC_ORDERS[index % 2]
