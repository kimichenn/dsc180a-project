from copy import deepcopy
import itertools
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ledger


class LedgerTests(unittest.TestCase):
    def test_hand_computed_cases(self):
        for world, budget in zip(ledger.smoke_cases(), (100, 185, 840, -30, 200)):
            rows = world["contexts"]["example"]
            self.assertEqual(ledger.solve(rows)[0], {"budget_k": budget})
            self.assertEqual(ledger.reference_solve(rows), {"budget_k": budget})

    def test_exhaustive_small_withdrawal_forests_against_truth_assignments(self):
        # Enumerate every legal unique-target graph over two updates and three withdrawals.
        cases = 0
        for targets in itertools.product(range(2, 4), range(2, 5), range(2, 6)):
            if len(set(targets)) != 3:
                continue
            rows = [ledger.record(1, "initial", amount_k=100),
                    ledger.record(2, "adjustment", amount_k=25), ledger.record(3, "adjustment", amount_k=-15)]
            rows += [ledger.record(i, "withdrawal", target=f"R{target:05d}") for i, target in zip(range(4, 7), targets)]
            # Third oracle: brute-force all active assignments satisfying the definition.
            valid = []
            for bits in itertools.product((False, True), repeat=5):
                active = {f"R{i:05d}": bit for i, bit in zip(range(2, 7), bits)}
                if all(active[row["id"]] == (not any(active[w["id"]] for w in rows
                       if w["type"] == "withdrawal" and w["target"] == row["id"])) for row in rows[1:]):
                    valid.append(100 + 25 * active["R00002"] - 15 * active["R00003"])
            self.assertEqual(len(valid), 1)
            self.assertEqual(ledger.solve(rows)[0]["budget_k"], valid[0])
            self.assertEqual(ledger.reference_solve(rows)["budget_k"], valid[0])
            cases += 1
        self.assertGreater(cases, 5)

    def test_generated_worlds_preserve_active_updates_and_record_positions(self):
        for seed in range(100):
            world = ledger.generate(seed, records=80)
            conflict = world["contexts"]["RG"]
            expected, active = ledger.solve(conflict)
            for context, rows in world["contexts"].items():
                self.assertEqual(ledger.solve(rows)[0], expected)
                self.assertEqual(ledger.reference_solve(rows), expected)
                self.assertEqual(len(rows), 80)
                for original, candidate in zip(conflict, rows):
                    for field in ("id", "author", "project"):
                        self.assertEqual(original[field], candidate[field])
                    if original["type"] in {"initial", "adjustment"} and active[original["id"]]:
                        self.assertEqual(original, candidate)
                if context in {"C", "R"}:
                    self.assertFalse(any("claimed_budget_k" in r for r in rows))
                if context in {"C", "G"}:
                    self.assertFalse(any(r["type"] == "withdrawal" for r in rows))
            self.assertTrue(all(r.get("claimed_budget_k") != expected["budget_k"] for r in conflict))

    def test_full_size_worlds_are_dense_and_deterministic(self):
        for seed in range(300000, 300005):
            world = ledger.generate(seed)
            self.assertEqual(world, ledger.generate(seed))
            info = world["diagnostics"]
            self.assertEqual(info["record_counts"]["adjustment"], 1439)
            self.assertEqual(info["record_counts"]["withdrawal"], 480)
            self.assertEqual(info["gossip_records"], 960)
            self.assertGreater(info["surviving_adjustments"], 1000)
            self.assertGreater(info["nested_withdrawals"], 100)

    def test_invalid_references_authority_and_later_resets_rejected(self):
        base = ledger.smoke_cases()[2]["contexts"]["example"]
        mutations = [(2, "target", "R00001"), (2, "target", "R00004"),
                     (3, "target", "R00002"), (1, "author", "Planning Team"), (1, "type", "initial")]
        for index, key, value in mutations:
            rows = deepcopy(base)
            rows[index][key] = value
            with self.assertRaises(ValueError):
                ledger.solve(rows)

    def test_terminal_answer_only_and_error_taxonomy(self):
        expected = {"budget_k": 840}
        self.assertEqual(ledger.score("800 + 40 = 840.\nANSWER: $840K", expected)["outcome"], "correct")
        wrong = ledger.score("An intermediate result is 840.\nANSWER: $800K", expected)
        self.assertEqual(wrong["outcome"], "wrong_budget")
        self.assertEqual(wrong["error_k"], -40)
        self.assertEqual(wrong["absolute_error_k"], 40)
        self.assertTrue(ledger.score("ANSWER: $-30K", {"budget_k": -30})["correct"])
        for text in ("ANSWER: $840K\nANSWER: $800K", "ANSWER: $840K\nLater: 800", "840",
                     "ANSWER: $840.0K", "ANSWER: $0840K", "ANSWER: $1,000K", "ANSWER: $840K extra"):
            self.assertEqual(ledger.score(text, expected)["outcome"], "malformed_output", text)
        self.assertEqual(ledger.score("ANSWER: ABSTAIN", expected)["outcome"], "abstained")
        self.assertEqual(ledger.score("", expected)["outcome"], "missing_output")

    def test_length_matching_keeps_question_last_and_records_intact(self):
        world = ledger.generate(300000)
        originals = {key: ledger.render(rows) for key, rows in world["contexts"].items()}
        counter = ledger.TokenCounter({"kind": "characters", "characters_per_token": 4})
        padded, counts = ledger.match_texts(originals, counter, before=ledger.QUESTION)
        self.assertLessEqual((max(counts.values()) - min(counts.values())) / max(counts.values()), .02)
        for key, text in padded.items():
            self.assertEqual(text.split("End of ledger.")[0], originals[key].split("End of ledger.")[0])
            self.assertEqual(text.strip().splitlines()[-1], originals[key].strip().splitlines()[-1])
            self.assertEqual(text.count(ledger.QUESTION), 1)


if __name__ == "__main__":
    unittest.main()
