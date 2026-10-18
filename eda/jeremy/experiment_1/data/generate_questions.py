"""Add generated evaluation questions to scenarios.json.

Hand-authored questions (provenance "eda") are kept unchanged. Previously generated
questions are replaced, so rerunning with the same seed reproduces the same file.
"""

import argparse
import itertools
import json
from pathlib import Path
import random
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import study

SCENARIOS = HERE / "scenarios.json"
HOURS = "hours after the start of Monday"

BASIC_DOMAINS = [
    # domain, metric, unit, comparisons, low, high, step
    ("inventory", "stock count", "units", ["larger"], 50, 400, 10),
    ("temperature", "temperature", "degrees Celsius", ["larger", "smaller"], 20, 120, 5),
    ("delivery", "arrival time", HOURS, ["smaller"], 2, 40, 1),
    ("duration", "processing duration", "minutes", ["smaller"], 20, 120, 5),
    ("capacity", "seating capacity", "seats", ["larger"], 20, 200, 5),
    ("cost", "price", "dollars", ["smaller"], 10, 90, 2),
    ("scheduling", "start time", HOURS, ["smaller"], 2, 40, 1),
]

CALCULATION_DOMAINS = ["subtract", "add", "divide_floor", "multiply"]

NAMES = """
Acacia Agate Alder Amber Anchor Anvil Arbor Arrow Ash Atlas Badger Basil Bay Beacon Beech
Bison Bluff Bramble Breeze Brick Bristle Cairn Calla Canary Canyon Cardinal Cascade Cinder
Clay Cliff Comet Condor Copper Coral Cove Crane Crest Crocus Cypress Dahlia Daisy Delta
Dove Drift Eagle Echo Egret Falcon Fennel Finch Fjord Flora Forge Fox Frost Garnet Gecko
Ginger Glacier Glen Granite Gull Harbor Hawk Heath Hemlock Holly Hollow Iris Ivy Jade Jay
Kestrel Kite Lagoon Lark Laurel Lilac Lily Lotus Lupine Lynx Magnolia Marble Marsh Marigold
Merlin Mesa Mica Mint Moss Nettle Oak Ocelot Onyx Orchid Osprey Otter Pansy Peony Pepper
Pike Plover Plum Poppy Prairie Puffin Quail Quill Raven Ridge Ripple River Rook Rose Ruby
Rush Saffron Sapphire Shale Sierra Slate Sparrow Starling Stone Summit Swan Sycamore Tansy
Teal Tern Thorn Thyme Tide Topaz Tulip Tundra Vale Verbena Vireo Wave Wren Yew Zinnia
Alcove Bayou Birchwood Bluebell Bobcat Boulder Briarwood Buckeye Butte Caraway Cedarline
Chert Cobble Cormorant Cottonwood Cranberry Dogwood Driftwood Elmira Fescue Foxglove
Gannet Gravel Hazelnut Heather Hickory Jasmine Kelp Lichen Linnet Loam Mallard Mangrove
Meadowlark Nutmeg Oriole Paprika Pelican Pinyon Quince Redwood Rosemary Rowan Sandpiper
Sedge Sorghum Spinel Tamarack Tarragon Thrush Tupelo Warbler Wisteria Woodbine
""".split()


def win(a, b, comparison):
    if a == b:
        return None
    return "a" if (a > b) == (comparison == "larger") else "b"


def grid(rng, low, high, step):
    return rng.randrange(low, high + 1, step)


def basic_values(rng, low, high, step, comparison):
    while True:
        other = grid(rng, low, high, step)
        correct, misleading = grid(rng, low, high, step), grid(rng, low, high, step)
        gaps = [abs(correct - other), abs(misleading - other), abs(correct - misleading)]
        if min(gaps) < 2 * step:
            continue
        right, wrong = win(correct, other, comparison), win(misleading, other, comparison)
        if right and wrong and right != wrong:
            return correct, misleading, other


def calculation_values(rng, operation):
    """Return values where the calculation flips the raw comparison and the
    misleading claim leads to the same answer as skipping the calculation."""
    while True:
        if operation == "subtract":
            pa, pb = grid(rng, 5, 120, 5), grid(rng, 5, 120, 5)
            correct, misleading, other = (grid(rng, 50, 400, 5) for _ in range(3))
            comparison, low = "larger", 10
        elif operation == "add":
            pa, pb = rng.randint(1, 12), rng.randint(1, 12)
            correct, misleading, other = (rng.randint(2, 30) for _ in range(3))
            comparison, low = "smaller", 1
        elif operation == "divide_floor":
            pa, pb = rng.randint(2, 9), rng.randint(2, 9)
            correct, misleading = pa * rng.randint(10, 60), pa * rng.randint(10, 60)
            other = pb * rng.randint(10, 60)
            comparison, low = "larger", 1
        else:
            pa, pb = rng.randint(2, 12), rng.randint(2, 12)
            correct, misleading, other = (rng.randint(5, 60) for _ in range(3))
            comparison, low = "larger", 1
        if pa == pb or len({correct, misleading, other}) < 3:
            continue
        ca, ma, cb = (study.calculate(v, operation, p) for v, p in
                      ((correct, pa), (misleading, pa), (other, pb)))
        if min(ca, ma, cb) < low or min(abs(ca - cb), abs(ma - cb)) < 2:
            continue
        right, raw = win(ca, cb, comparison), win(correct, other, comparison)
        if right and raw and right != raw and win(ma, cb, comparison) == raw:
            return correct, misleading, other, pa, pb, comparison


def hours(n):
    return f"{n} hour" if n == 1 else f"{n} hours"


def calculation_text(operation, a, b, pa, pb):
    if operation == "subtract":
        return ("inventory", "stock count", "units",
                f"{a} must keep {pa} units in reserve. {b} must keep {pb} units in reserve. "
                "Each can ship its stock count minus its own reserve.",
                f"Which entity can ship more units, {a} or {b}?")
    if operation == "add":
        return ("delivery", "arrival time", HOURS,
                f"After arrival, {a} needs {hours(pa)} of processing and {b} needs {hours(pb)}. "
                "Each is ready for collection at its arrival time plus its own processing time.",
                f"Which entity is ready for collection earlier, {a} or {b}?")
    if operation == "divide_floor":
        return ("production", "available material", "units",
                f"{a} uses {pa} material units per kit. {b} uses {pb} material units per kit. "
                "Only whole kits count; divide available material by the entity-specific "
                "units per kit and round down.",
                f"Which entity can make more complete kits, {a} or {b}?")
    return ("revenue", "number of items sold", "items",
            f"Each item sold by {a} earns {pa} dollars. Each item sold by {b} earns {pb} dollars. "
            "Revenue is number of items sold times its own price per item.",
            f"Which entity earns more revenue, {a} or {b}?")


def generate(existing, per_cell, seed):
    rng = random.Random(seed)
    used = {q[k] for q in existing for k in ("entity_a", "entity_b")}
    names = [n for n in dict.fromkeys(NAMES) if n not in used]
    needed = 2 * 4 * per_cell
    if len(names) < needed:
        raise ValueError(f"Need {needed} unused entity names, only have {len(names)}.")
    rng.shuffle(names)
    pairs = iter(zip(names[::2], names[1::2]))
    number = max(int(q["question_id"][1:]) for q in existing if q["phase"] == "evaluation")
    orders = itertools.cycle(["governing_first", "competing_first"])
    questions = []
    for subtype, difficulty in itertools.product(("distractor", "update"), ("basic", "calculation")):
        domains = BASIC_DOMAINS if difficulty == "basic" else CALCULATION_DOMAINS
        for i in range(per_cell):
            a, b = next(pairs)
            if difficulty == "basic":
                domain, metric, unit, comparisons, low, high, step = domains[i % len(domains)]
                comparison = comparisons[(i // len(domains)) % len(comparisons)]
                correct, misleading, other = basic_values(rng, low, high, step, comparison)
                operation, pa, pb = "identity", 0, 0
                rule = "Compare the stated values directly."
                question = f"Which entity has the {comparison} {metric}, {a} or {b}?"
            else:
                operation = domains[i % len(domains)]
                correct, misleading, other, pa, pb, comparison = calculation_values(rng, operation)
                domain, metric, unit, rule, question = calculation_text(operation, a, b, pa, pb)
            number += 1
            questions.append({
                "question_id": f"E{number:02d}", "phase": "evaluation", "subtype": subtype,
                "difficulty": difficulty, "domain": domain, "entity_a": a, "entity_b": b,
                "metric": metric, "unit": unit, "correct_value": correct,
                "misleading_value": misleading, "other_value": other, "operation": operation,
                "parameter_a": pa, "parameter_b": pb, "comparison": comparison,
                "calculation_rule": rule, "question": question, "claim_order": next(orders),
                "provenance": "generated",
            })
    return questions


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-cell", type=int, default=20,
                        help="New evaluation questions per subtype × difficulty cell")
    parser.add_argument("--seed", type=int, default=180)
    args = parser.parse_args(argv)
    existing = [q for q in json.loads(SCENARIOS.read_text()) if q["provenance"] != "generated"]
    questions = existing + generate(existing, args.per_cell, args.seed)
    study.validate_questions(questions)
    SCENARIOS.write_text(json.dumps(questions, indent=2) + "\n", encoding="utf-8")
    evaluation = sum(q["phase"] == "evaluation" for q in questions)
    print(f"Wrote {len(questions)} questions ({evaluation} evaluation) to {SCENARIOS}")


if __name__ == "__main__":
    main()
