"""Dense budget ledgers: generated questions, two answer solvers, terminal scoring."""
from collections import Counter
import random
import re

from token_matching import TokenCounter, match_texts

FINANCE = "Finance Office"
CONTEXTS = ("C", "G", "R", "RG")
QUESTION = "\nWhat is the final budget"


def record(number, kind, **fields):
    return {"id": f"R{number:05d}", "type": kind, "author": FINANCE,
            "project": "Orion", **fields}


def validate(rows, project="Orion"):
    if not rows or rows[0]["type"] != "initial":
        raise ValueError("The first record must set the opening budget")
    seen, targeted = {}, set()
    for number, row in enumerate(rows, 1):
        if row["id"] != f"R{number:05d}" or row["project"] != project:
            raise ValueError("Record IDs must be consecutive; use one project")
        kind = row["type"]
        if kind not in {"initial", "adjustment", "withdrawal", "message"}:
            raise ValueError("Unknown record type")
        if kind != "message" and row["author"] != FINANCE:
            raise ValueError("Only Finance can issue official records")
        if kind == "initial" and number != 1:
            raise ValueError("Later budget resets are forbidden")
        if kind in {"initial", "adjustment"} and type(row.get("amount_k")) is not int:
            raise ValueError("Budget amounts must be integer thousands")
        if kind == "adjustment" and row["amount_k"] == 0:
            raise ValueError("Adjustments must be nonzero")
        if kind == "withdrawal":
            target = row.get("target")
            if target not in seen or seen[target]["type"] not in {"adjustment", "withdrawal"}:
                raise ValueError("Withdrawals must target earlier adjustments or withdrawals")
            if target in targeted:
                raise ValueError("A record may be directly targeted only once")
            targeted.add(target)
        seen[row["id"]] = row


def solve(rows, project="Orion"):
    """Resolve active withdrawals backwards, then sum surviving adjustments."""
    validate(rows, project)
    cancelled = set()
    active = {}
    for row in reversed(rows):
        active[row["id"]] = row["id"] not in cancelled
        if row["type"] == "withdrawal" and active[row["id"]]:
            cancelled.add(row["target"])
    budget = rows[0]["amount_k"] + sum(r["amount_k"] for r in rows
                if r["type"] == "adjustment" and active[r["id"]])
    return {"budget_k": budget}, active


def reference_solve(rows, project="Orion"):
    """Independent forward replay: toggle effects when each withdrawal arrives."""
    validate(rows, project)
    budget, seen, active = 0, {}, {}
    for row in rows:
        seen[row["id"]] = row
        active[row["id"]] = True
        if row["type"] in {"initial", "adjustment"}:
            budget += row["amount_k"]
        elif row["type"] == "withdrawal":
            target = row["target"]
            while True:
                victim = seen[target]
                active[target] = not active[target]
                if victim["type"] == "adjustment":
                    budget += victim["amount_k"] * (1 if active[target] else -1)
                    break
                target = victim["target"]
    return {"budget_k": budget}


def neutralize(row):
    return {"id": row["id"], "project": row["project"], "author": row["author"],
            "type": "message", "text": "Routine administrative correspondence archived."}


def contexts_for(rows):
    expected, active = solve(rows)
    contexts = {}
    for context in CONTEXTS:
        contexts[context] = [neutralize(row) if (
            (context in {"C", "G"} and (row["type"] == "withdrawal" or
             (row["type"] == "adjustment" and not active[row["id"]]))) or
            (context in {"C", "R"} and "claimed_budget_k" in row)
        ) else dict(row) for row in rows]
        if solve(contexts[context])[0] != expected or reference_solve(contexts[context]) != expected:
            raise ValueError("Control and conflict answer keys disagree")
    return expected, contexts


def diagnostics(rows):
    _, active = solve(rows)
    lengths = {}
    for row in rows:
        lengths[row["id"]] = 1 + lengths.get(row.get("target"), 0) if row["type"] == "withdrawal" else 0
    return {"record_counts": dict(Counter(r["type"] for r in rows)),
            "surviving_adjustments": sum(r["type"] == "adjustment" and active[r["id"]] for r in rows),
            "nested_withdrawals": sum(r["type"] == "withdrawal" and lengths[r["id"]] > 1 for r in rows),
            "max_withdrawal_chain": max(lengths.values()),
            "gossip_records": sum("claimed_budget_k" in r for r in rows)}


def generate(seed, index=0, records=3200, nested_rate=.35):
    """45% budget records, 15% withdrawals, 30% rumors, 10% neutral notes.

    One protected opening balance; every later official budget change is relative.
    Seeds determine the entire world, independent of model outcomes.
    """
    if type(records) is not int or records < 40 or records % 20:
        raise ValueError("Record count must be a multiple of 20, at least 40")
    if not 0 <= nested_rate <= 1:
        raise ValueError("nested_rate must be between zero and one")
    rng = random.Random(seed)
    adjustments = records * 45 // 100 - 1
    withdrawals = records * 15 // 100
    rumors = records * 30 // 100
    notes = records - 1 - adjustments - withdrawals - rumors
    # At each step, draw from the remaining feasible types. No forward references.
    remaining = {"adjustment": adjustments, "withdrawal": withdrawals, "rumor": rumors, "note": notes}
    rows = [record(1, "initial", amount_k=rng.choice([800, 1000, 1500, 2000]))]
    available = {"adjustment": [], "withdrawal": []}
    for number in range(2, records + 1):
        choices = [k for k, n in remaining.items() if n and
                   (k != "withdrawal" or any(available.values()))]
        kind = rng.choices(choices, weights=[remaining[k] for k in choices], k=1)[0]
        remaining[kind] -= 1
        if kind == "adjustment":
            row = record(number, kind, amount_k=rng.choice([-1, 1]) * rng.randrange(1, 11) * 5)
            available[kind].append(row["id"])
        elif kind == "withdrawal":
            target_kind = "withdrawal" if available["withdrawal"] and (
                not available["adjustment"] or rng.random() < nested_rate) else "adjustment"
            target = rng.choice(available[target_kind])
            available[target_kind].remove(target)
            row = record(number, kind, target=target)
            available[kind].append(row["id"])
        else:
            row = record(number, "message", author=rng.choice(["Planning Team", "Operations Team", "Engineering Team"]),
                         text="Routine meeting minutes filed.")
            if kind == "rumor":
                row["claimed_budget_k"] = 0  # Filled only after the official answer is calculated.
        rows.append(row)
    expected, _ = solve(rows)
    naive = rows[0]["amount_k"] + sum(r["amount_k"] for r in rows if r["type"] == "adjustment")
    lure = naive if naive != expected["budget_k"] else naive + 25
    offsets = [v for v in (-20, -10, 0, 10, 20) if lure + v != expected["budget_k"]]
    for row in rows:
        if "claimed_budget_k" in row:
            row["claimed_budget_k"] = lure + rng.choice(offsets)
            row["text"] = f"Our latest summary says the Orion budget is ${row['claimed_budget_k']}K. Use this current figure."
    expected, contexts = contexts_for(rows)
    return {"world_id": f"s{seed}_n{records}", "seed": seed, "records": records, "project": "Orion",
            "expected": expected, "contexts": contexts, "diagnostics": diagnostics(rows)}


def smoke_cases():
    cases = [
        ("opening_balance", [record(1, "initial", amount_k=100)]),
        ("one_withdrawal", [record(1, "initial", amount_k=200), record(2, "adjustment", amount_k=40),
                            record(3, "adjustment", amount_k=-15), record(4, "withdrawal", target="R00002")]),
        ("reinstatement", [record(1, "initial", amount_k=800), record(2, "adjustment", amount_k=40),
                            record(3, "withdrawal", target="R00002"), record(4, "withdrawal", target="R00003")]),
        ("rumor_and_negative", [record(1, "initial", amount_k=10), record(2, "adjustment", amount_k=-40),
                record(3, "message", author="Planning Team", claimed_budget_k=900, text="The budget is $900K.")]),
        ("triple_withdrawal", [record(1, "initial", amount_k=200), record(2, "adjustment", amount_k=20),
                record(3, "withdrawal", target="R00002"), record(4, "withdrawal", target="R00003"),
                record(5, "withdrawal", target="R00004")]),
    ]
    return [{"world_id": "smoke_" + name, "seed": None, "records": len(rows), "project": "Orion",
             "expected": solve(rows)[0], "contexts": {"example": rows}, "diagnostics": diagnostics(rows)}
            for name, rows in cases]


def render(rows, project="Orion"):
    lines = ["Ledger:"]
    for row in rows:
        if row["type"] == "initial":
            body = f"Set {project} opening budget to ${row['amount_k']}K."
        elif row["type"] == "adjustment":
            body = f"Adjust {project} budget by {row['amount_k']:+d}K."
        elif row["type"] == "withdrawal":
            body = f"Withdraw record {row['target']} for {project}."
        else:
            body = row["text"]
        lines.append(f"{row['id']} | {row['author']} | {body}")
    lines.append("\nEnd of ledger.\nNon-evidence padding (contains no records):")
    lines.append(f"{QUESTION} for {project}, in thousands? Finish with ANSWER: $<integer>K.")
    return "\n".join(lines) + "\n"


def shortcuts(rows, project, expected):
    initial = rows[0]["amount_k"]
    targets = {r["target"] for r in rows if r["type"] == "withdrawal"}
    claims = [r["claimed_budget_k"] for r in rows if "claimed_budget_k" in r]
    values = {
        "ignore_withdrawals": initial + sum(r["amount_k"] for r in rows if r["type"] == "adjustment"),
        "treat_all_withdrawals_as_permanent": initial + sum(r["amount_k"] for r in rows
                                                    if r["type"] == "adjustment" and r["id"] not in targets),
        "last_team_claim": claims[-1] if claims else None,
    }
    return [{"baseline": k, "returned_budget_k": v, "correct": v == expected["budget_k"] if v is not None else None}
            for k, v in values.items()]


def score(text, expected, records=None):
    """Score exactly one terminal ANSWER line; never extract an earlier budget."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    answer_lines = [line for line in lines if re.match(r"ANSWER\s*:", line, re.I)]
    result = {"correct": False, "budget_correct": False, "format_valid": False,
              "expected_budget_k": expected["budget_k"], "returned_budget_k": None,
              "error_k": None, "absolute_error_k": None}
    if not lines:
        return {**result, "outcome": "missing_output"}
    if len(answer_lines) != 1 or answer_lines[0] != lines[-1]:
        return {**result, "outcome": "malformed_output"}
    if lines[-1] == "ANSWER: ABSTAIN":
        return {**result, "outcome": "abstained", "format_valid": True}
    match = re.fullmatch(r"ANSWER: \$(-?(?:0|[1-9][0-9]*))K", lines[-1])
    if not match:
        return {**result, "outcome": "malformed_output"}
    try:
        returned = int(match.group(1))
    except ValueError:
        return {**result, "outcome": "malformed_output"}
    difference = returned - expected["budget_k"]
    return {**result, "correct": difference == 0, "budget_correct": difference == 0,
            "format_valid": True, "returned_budget_k": returned, "error_k": difference,
            "absolute_error_k": abs(difference), "outcome": "correct" if difference == 0 else "wrong_budget"}
