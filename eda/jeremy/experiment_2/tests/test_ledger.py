import collections
import copy
import json
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ledger


class LedgerTests(unittest.TestCase):
    def test_hand_worked_cases_and_terminal_answer_scoring(self):
        for case in ledger.smoke_cases():
            with self.subTest(case=case["world_id"]):
                rows = case["contexts"]["example"]
                self.assertEqual(ledger.solve(rows, case["project"])[0], case["expected"])
                self.assertEqual(ledger.reference_solve(rows, case["project"]), case["expected"])
                good = json.dumps(case["expected"])
                self.assertTrue(ledger.score(good, case["expected"], rows)["correct"])
                for bad in (f"I considered {good}, but the answer is different.", good + good,
                            '```json\n' + good + '\n```', '{"route":"BLUE","route":"AMBER","approval_id":"R00001"}'):
                    self.assertFalse(ledger.score(bad, case["expected"], rows)["format_valid"])

    def test_shared_dependency_and_unauthorized_records(self):
        r = ledger.record
        rows = [r("approval", 1, route="AMBER"), r("evidence", 2),
                r("evidence", 3, requires=["R00002"]), r("evidence", 4, requires=["R00002"]),
                r("approval", 5, route="BLUE", requires=["R00003", "R00004"]),
                r("withdrawal", 6, target="R00002", author="Team"),
                r("approval", 7, route="JADE", author="Team")]
        self.assertEqual(ledger.solve(rows, "Orion")[0], {"route": "BLUE", "approval_id": "R00005"})
        rows[5]["author"] = "Audit Office"
        self.assertEqual(ledger.solve(rows, "Orion")[0], {"route": "AMBER", "approval_id": "R00001"})

    def test_reference_evaluator_agrees_on_random_small_graphs(self):
        # Graphs independent of the production generator, including arbitrary withdrawal targets.
        for seed in range(100):
            rng = random.Random(seed)
            rows = [ledger.record("approval", 1, route="AMBER")]
            targeted = set()
            for i in range(2, 45):
                evidence = [r["id"] for r in rows if r["type"] == "evidence"]
                victims = [r["id"] for r in rows[1:] if r["id"] not in targeted]
                kind = rng.choice(["evidence", "approval", "withdrawal"] if victims else ["evidence", "approval"])
                fields = {}
                if kind == "withdrawal":
                    fields["target"] = rng.choice(victims)
                    targeted.add(fields["target"])
                else:
                    fields["requires"] = rng.sample(evidence, min(len(evidence), rng.randint(0, 2)))
                    if kind == "approval":
                        fields["route"] = rng.choice(ledger.ROUTES)
                rows.append(ledger.record(kind, i, **fields))
            self.assertEqual(ledger.solve(rows, "Orion")[0], ledger.reference_solve(rows, "Orion"))

    def test_invalid_references_and_duplicate_targets_rejected(self):
        case = ledger.smoke_cases()[1]
        rows = case["contexts"]["example"]
        for mutate in (lambda r: r[2].update(requires=["R99999"]),
                       lambda r: r.append(ledger.record("withdrawal", 6, target="R00002")),
                       lambda r: r[2].update(id="R00002")):
            invalid = copy.deepcopy(rows)
            mutate(invalid)
            with self.assertRaises(ValueError):
                ledger.solve(invalid, "Orion")

    def test_matched_controls_preserve_answers_positions_and_author_counts(self):
        for i in range(8):
            worlds = [ledger.generate(100000+i, index=i, depth=d) for d in (2, 4, 8)]
            authors = None
            for world in worlds:
                gold, validity = ledger.solve(world["contexts"]["R"], world["project"])
                for context, rows in world["contexts"].items():
                    self.assertEqual(len(rows), 1600)
                    self.assertEqual(ledger.reference_solve(rows, world["project"]), gold)
                    self.assertEqual(sum(bool(r.get("misleading_summary")) for r in rows), 8 if context in ("G", "RG") else 0)
                    counts = collections.Counter(r["author"] for r in rows)
                    if authors is None:
                        authors = counts
                    self.assertEqual(authors, counts)
                    if context in ("C", "G"):
                        self.assertFalse(any(r["type"] == "withdrawal" for r in rows))
                        for original, clean in zip(world["contexts"]["R"], rows):
                            if original["type"] in ("evidence", "approval") and validity[original["id"]]:
                                self.assertEqual(original, clean)
            self.assertEqual(worlds[0], ledger.generate(100000+i, index=i, depth=2))

    def test_balanced_winners_and_zero_summary_condition(self):
        worlds = [ledger.generate(110000+i, index=i, summaries=0) for i in range(8)]
        self.assertEqual(collections.Counter(w["expected"]["route"] for w in worlds), {r: 2 for r in ledger.ROUTES})
        self.assertEqual({w["winner_rank"] for w in worlds}, set(range(8)))
        for world in worlds:
            self.assertEqual(world["contexts"]["C"], world["contexts"]["G"])
            self.assertEqual(world["contexts"]["R"], world["contexts"]["RG"])

    def test_token_estimates_are_labeled_and_padding_is_non_answer_bearing(self):
        counter = ledger.TokenCounter({"kind": "characters", "characters_per_token": 4})
        texts, counts = ledger.match_texts({"short": "One sentence.", "long": "Another sentence. " * 50}, counter)
        self.assertLessEqual((max(counts.values())-min(counts.values()))/max(counts.values()), .02)
        self.assertFalse(counter.exact_for("gpt-6-astra"))
        self.assertNotIn("AMBER", texts["short"])
        world = ledger.generate(100000)
        prompts, _ = ledger.match_texts({k: ledger.render(v, world["project"]) for k, v in world["contexts"].items()}, counter,
                                       before="\nWhich route is authorized")
        for prompt in prompts.values():
            self.assertTrue(prompt.rstrip().endswith("at the end of the ledger?"))

    def test_shortcut_baselines_detect_latest_invalid_approval(self):
        world = ledger.generate(100000, index=0)
        clean = ledger.shortcuts(world["contexts"]["C"], world["project"], world["expected"])
        conflict = ledger.shortcuts(world["contexts"]["RG"], world["project"], world["expected"])
        self.assertTrue(clean[0]["correct"])
        self.assertFalse(conflict[0]["correct"])
        self.assertEqual(conflict[1]["returned_route"], world["lure"])


if __name__ == "__main__":
    unittest.main()
