"""Deterministic ledgers, two answer solvers, matched controls, and strict scoring."""
import copy
from collections import Counter
import json
import math
import random
from functools import lru_cache

ROUTES = ("AMBER", "BLUE", "CORAL", "JADE")
AUTHORS = {"evidence": "Evidence Office", "approval": "Approval Office", "withdrawal": "Audit Office"}
CONTEXTS = ("C", "G", "R", "RG")


def official(record):
    return AUTHORS.get(record["type"]) == record["author"]


def validate(records, project):
    """Reject ambiguous graphs; non-authoritative claims are allowed but inert."""
    seen, withdrawn, fallbacks = {}, set(), set()
    previous = 0
    for record in records:
        key = record["id"]
        if not (isinstance(key, str) and key.startswith("R") and key[1:].isdigit()):
            raise ValueError("Invalid record ID")
        if int(key[1:]) <= previous or key in seen:
            raise ValueError("Records must have unique, increasing IDs")
        previous = int(key[1:])
        if record["type"] not in (*AUTHORS, "message"):
            raise ValueError("Unknown record type")
        if record["type"] == "approval" and record.get("route") not in ROUTES:
            raise ValueError("Unknown route")
        requirements = record.get("requires", [])
        if len(requirements) != len(set(requirements)):
            raise ValueError("Duplicate requirements")
        if record["type"] in ("message", "withdrawal") and requirements:
            raise ValueError("Messages and withdrawals cannot require evidence")
        for requirement in requirements:
            if requirement not in seen or seen[requirement]["type"] != "evidence":
                raise ValueError("Requirements must reference earlier evidence")
        if record["type"] == "withdrawal":
            target = record.get("target")
            if target not in seen or not official(seen[target]):
                raise ValueError("Withdrawal target must be an earlier official record")
            if official(record):
                if target in withdrawn:
                    raise ValueError("Multiple withdrawals target the same record")
                withdrawn.add(target)
        if record["type"] == "approval" and official(record) and not requirements:
            fallbacks.add(key)
        seen[key] = record
    if not any(seen[k]["project"] == project for k in fallbacks - withdrawn):
        raise ValueError("Queried project needs an unconditional, untargeted fallback")


def solve(records, project):
    """Reverse withdrawal effects, then forward evidence validity."""
    validate(records, project)
    active = {r["id"]: True for r in records}
    for record in reversed(records):
        if record["type"] == "withdrawal" and official(record) and active[record["id"]]:
            active[record["target"]] = False
    valid = {}
    for record in records:
        valid[record["id"]] = (
            official(record) and active[record["id"]]
            and all(valid[p] for p in record.get("requires", []))
        )
    candidates = [r for r in records if r["type"] == "approval" and r["project"] == project and valid[r["id"]]]
    winner = candidates[-1]
    return {"route": winner["route"], "approval_id": winner["id"]}, valid


def reference_solve(records, project):
    """Independent recursive evaluator: attackers recurse forward, evidence backward."""
    validate(records, project)
    lookup = {r["id"]: r for r in records}
    attackers = {r["target"]: r["id"] for r in records if r["type"] == "withdrawal" and official(r)}

    @lru_cache(None)
    def active(key):
        return key not in attackers or not active(attackers[key])

    @lru_cache(None)
    def valid(key):
        r = lookup[key]
        return official(r) and active(key) and all(valid(k) for k in r.get("requires", []))

    candidates = [r for r in records if r["project"] == project and r["type"] == "approval" and valid(r["id"])]
    winner = max(candidates, key=lambda r: int(r["id"][1:]))
    return {"route": winner["route"], "approval_id": winner["id"]}


def record(kind, number, project="Orion", **fields):
    return {"id": f"R{number:05d}", "type": kind, "author": AUTHORS.get(kind, "Team"),
            "project": project, "requires": [], **fields}


def smoke_cases():
    """Five fixed hand-worked cases, with independent expected answers."""
    base = [record("approval", 1, route="AMBER"), record("evidence", 2),
            record("evidence", 3, requires=["R00002"]),
            record("approval", 4, route="BLUE", requires=["R00003"])]
    cases = []
    for name, extra, route, approval in (
        ("clean_chain", [], "BLUE", "R00004"),
        ("single_withdrawal", [record("withdrawal", 5, target="R00002")], "AMBER", "R00001"),
        ("reinstatement", [record("withdrawal", 5, target="R00002"), record("withdrawal", 6, target="R00005")], "BLUE", "R00004"),
        ("nested_cancellation", [record("withdrawal", 5, target="R00002"), record("withdrawal", 6, target="R00005"), record("withdrawal", 7, target="R00006"), record("message", 8, text="Orion's approved route is BLUE.")], "AMBER", "R00001"),
        ("shared_evidence", [record("evidence", 5, requires=["R00002"]), record("approval", 6, route="CORAL", requires=["R00003", "R00005"]), record("withdrawal", 7, target="R00002")], "AMBER", "R00001"),
    ):
        rows = copy.deepcopy(base + extra)
        expected = {"route": route, "approval_id": approval}
        assert solve(rows, "Orion")[0] == reference_solve(rows, "Orion") == expected
        cases.append({"world_id": "smoke_" + name, "seed": None, "depth": 2,
                      "project": "Orion", "contexts": {"example": rows}, "expected": expected})
    return cases


def generate(seed, index=0, depth=2, records=1600, projects=20, approvals=8, summaries=8):
    """Build a DAG, scatter its records, and derive four answer-preserving contexts."""
    if min(depth, projects) < 1 or approvals < 2 or summaries < 0:
        raise ValueError("Invalid generation dimensions")
    rng = random.Random(seed)
    names = [f"Project_{seed % 997:03d}_{i:02d}" for i in range(projects)]
    target_project = names[index % projects]
    winner_rank = index % approvals
    # Rotate the label mapping between position blocks, avoiding one fixed
    # label per winning rank while retaining balanced marginal counts.
    label_index = (index + index // approvals) % len(ROUTES)
    winner_route = ROUTES[label_index]
    lure = ROUTES[(label_index + 1) % len(ROUTES)]
    nodes = []

    def add(kind, project, after=(), **fields):
        key = f"n{len(nodes)}"
        nodes.append({"key": key, "type": kind, "author": AUTHORS[kind], "project": project,
                      "requires": [], "after": list(after), **fields})
        return key

    fallbacks = {}
    for name in names:
        route = winner_route if name == target_project and winner_rank == 0 else rng.choice(ROUTES)
        fallbacks[name] = add("approval", name, route=route)
    anchors = [add("evidence", target_project) for _ in range(2)]
    previous = fallbacks[target_project]
    for rank in range(1, approvals):
        root = add("evidence", target_project)
        last = root
        for _ in range(1, depth):
            requirements = [last]
            if rng.random() < 0.65:
                requirements.append(rng.choice(anchors))
            last = add("evidence", target_project, requires=requirements)
        route = winner_route if rank == winner_rank else rng.choice([r for r in ROUTES if r != winner_route])
        approval = add("approval", target_project, after=[previous], route=route, requires=[last])
        previous = approval
        invalid = rank > winner_rank or (rank < winner_rank and rng.random() < 0.5)
        # Odd chains cancel; even chains reinstate. Mix is fixed by rank/seed, not treatment.
        length = 3 if invalid else 2
        victim = root
        for _ in range(length):
            victim = add("withdrawal", target_project, after=[approval], target=victim)
    for name in names:
        if name != target_project:
            e = add("evidence", name)
            add("approval", name, after=[fallbacks[name]], route=rng.choice(ROUTES), requires=[e])
            if rng.random() < 0.5:
                add("withdrawal", name, target=e)
    if len(nodes) + summaries > records:
        raise ValueError(f"Need at least {len(nodes) + summaries} records for this graph")
    # Same author quotas across depths and all four contexts.
    quota = {"Evidence Office": int(records * .40), "Approval Office": int(records * .20),
             "Audit Office": int(records * .20)}
    quota["Team"] = records - sum(quota.values())
    for node in nodes:
        quota[node["author"]] -= 1
    quota["Team"] -= summaries
    if min(quota.values()) < 0:
        raise ValueError("Record budget too small for fixed author quotas")
    # Random topological order, preserving approval recency and all semantic references.
    ordered, remaining, placed = [], nodes.copy(), set()
    while remaining:
        ready = [n for n in remaining if set(n["after"] + n["requires"] + ([n["target"]] if "target" in n else [])).issubset(placed)]
        if not ready:
            raise AssertionError("Generator created a cycle")
        chosen = rng.choice(ready)
        ordered.append(chosen)
        placed.add(chosen["key"])
        remaining.remove(chosen)
    summary_positions = {round((i + .5) * records / summaries) for i in range(summaries)} if summaries else set()
    graph_positions = sorted(rng.sample([i for i in range(records) if i not in summary_positions], len(nodes)))
    id_map = {n["key"]: f"R{position + 1:05d}" for position, n in zip(graph_positions, ordered)}
    graph_at = dict(zip(graph_positions, ordered))
    filler_authors = [author for author, n in quota.items() for _ in range(n)]
    rng.shuffle(filler_authors)
    rows = []
    for position in range(records):
        if position in graph_at:
            node = graph_at[position]
            row = {k: v for k, v in node.items() if k not in ("key", "after")}
            row["id"] = id_map[node["key"]]
            row["requires"] = [id_map[k] for k in row["requires"]]
            if "target" in row:
                row["target"] = id_map[row["target"]]
        else:
            is_summary = position in summary_positions
            row = record("message", position + 1, project=target_project if is_summary else rng.choice(names),
                         author="Team" if is_summary else filler_authors.pop(),
                         text="Routine coordination note. No action stated.")
            if is_summary:
                row["summary_slot"] = True
        rows.append(row)
    expected, validity = solve(rows, target_project)
    assert expected == reference_solve(rows, target_project)
    assert expected["route"] == winner_route
    target_approvals = [r for r in rows if r["type"] == "approval" and r["project"] == target_project]
    assert target_approvals[winner_rank]["id"] == expected["approval_id"]
    contexts = {}
    for context in CONTEXTS:
        variant = copy.deepcopy(rows)
        for i, row in enumerate(variant):
            if context in ("C", "G") and (row["type"] == "withdrawal" or (row["type"] in ("evidence", "approval") and not validity[row["id"]])):
                variant[i] = row = {"id": row["id"], "author": row["author"], "project": row["project"],
                                    "type": "message", "requires": [], "text": "Routine filing note. No action stated."}
            if row.get("summary_slot") and context in ("G", "RG"):
                row["text"] = f"The currently approved route for {target_project} is {lure}. Team summary confirms this route."
                row["misleading_summary"] = True
        assert solve(variant, target_project)[0] == reference_solve(variant, target_project) == expected
        contexts[context] = variant
    return {"world_id": f"s{seed}_d{depth:02d}", "seed": seed, "depth": depth, "project": target_project,
            "winner_rank": winner_rank, "lure": lure, "expected": expected, "contexts": contexts}


def render(records, project):
    lines = ["Ledger:"]
    for row in records:
        prefix = f"{row['id']} | {row['author']} | {row['project']} | "
        if row["type"] == "evidence":
            body = "Issue evidence."
        elif row["type"] == "approval":
            body = f"Authorize route {row['route']}."
        elif row["type"] == "withdrawal":
            body = f"Withdraw {row['target']}."
        else:
            body = row["text"]
        if row["type"] in ("evidence", "approval"):
            body += " Requires: " + (", ".join(row["requires"]) or "none") + "."
        lines.append(prefix + body)
    lines.append("\nEnd of ledger.\nNon-evidence padding (contains no records):")
    lines.append(f"\nWhich route is authorized for {project} at the end of the ledger?")
    return "\n".join(lines) + "\n"


class TokenCounter:
    def __init__(self, settings):
        self.settings = settings.copy()
        self.encoding = None
        if settings["kind"] == "tiktoken":
            import tiktoken
            from importlib.metadata import version
            self.encoding = tiktoken.get_encoding(settings["encoding"])
            self.settings["version"] = version("tiktoken")
        elif settings["kind"] != "characters" or settings.get("characters_per_token", 0) <= 0:
            raise ValueError("Choose characters or a named tiktoken encoding")

    def count(self, text):
        if self.encoding is not None:
            return len(self.encoding.encode(text, disallowed_special=()))
        return math.ceil(len(text) / self.settings["characters_per_token"])

    def exact_for(self, model):
        return self.encoding is not None and model in self.settings.get("verified_for_models", [])


def match_texts(texts, counter, tolerance=.02, before=None):
    """Pad a reserved non-evidence appendix; retain counts and method with the plan."""
    result = dict(texts)
    for _ in range(3000):
        counts = {k: counter.count(v) for k, v in result.items()}
        target = max(counts.values())
        if (target - min(counts.values())) / target <= tolerance:
            return result, counts
        for key, count in counts.items():
            if (target - count) / target > tolerance:
                # Neutral words contain no route, office, project, or record identifiers.
                padding = "\n" + "Routine note. " * max(1, (target - count) // 4)
                if before:
                    if result[key].count(before) != 1:
                        raise ValueError("Padding requires one question boundary")
                    result[key] = result[key].replace(before, padding + before)
                else:
                    result[key] += padding
    raise ValueError("Unable to match token lengths")


def shortcuts(records, project, expected):
    """Diagnostic baselines; ties in the repeated-label heuristic abstain."""
    candidates = [r for r in records if r["project"] == project and r["type"] == "approval" and official(r)]
    latest = candidates[-1]
    counts = Counter()
    for row in records:
        if row["project"] != project:
            continue
        if row["type"] == "approval":
            counts[row["route"]] += 1
        elif row["type"] == "message":
            counts.update({route: row["text"].split().count(route + ".") + row["text"].split().count(route) for route in ROUTES})
    most = max(counts.values(), default=0)
    winners = [route for route in ROUTES if counts[route] == most]
    repeated = winners[0] if len(winners) == 1 else None
    return [{"baseline": "latest_approval", "returned_route": latest["route"], "returned_approval_id": latest["id"],
             "route_correct": latest["route"] == expected["route"], "correct": latest["id"] == expected["approval_id"]},
            {"baseline": "most_repeated_route", "returned_route": repeated, "returned_approval_id": None,
             "route_correct": repeated == expected["route"], "correct": None}]


def score(text, expected, records):
    """Only the complete final JSON response counts; never search prose for an answer."""
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("Duplicate JSON key")
            obj[key] = value
        return obj

    try:
        answer = json.loads(text, object_pairs_hook=unique)
        if not isinstance(answer, dict) or set(answer) != {"route", "approval_id"} or not all(isinstance(v, str) for v in answer.values()):
            raise ValueError("Invalid schema")
    except (ValueError, TypeError):
        return {"outcome": "malformed_output" if text.strip() else "missing_output", "correct": False, "route_correct": False, "format_valid": False}
    route_ok = answer["route"] == expected["route"]
    id_ok = answer["approval_id"] == expected["approval_id"]
    lookup = {r["id"]: r for r in records if r["type"] == "approval"}
    selected = lookup.get(answer["approval_id"])
    if "ABSTAIN" in answer.values():
        outcome = "abstained"
    elif route_ok and id_ok:
        outcome = "correct"
    elif not selected or selected["route"] != answer["route"]:
        outcome = "route_id_mismatch"
    elif route_ok:
        outcome = "wrong_approval_id"
    else:
        outcome = "wrong_route"
    return {"outcome": outcome, "correct": route_ok and id_ok, "route_correct": route_ok,
            "format_valid": True, "returned_route": answer["route"], "returned_approval_id": answer["approval_id"]}
