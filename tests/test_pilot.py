import unittest

from experiment.pilot import paired_gains
from experiment.runs import Trial


def trials_for(model="gpt", repeats=1):
    return [Trial(f"{model}_{version}_{arm}_{repeat}", 0, "world", version, arm, model, repeat)
            for version in ("R", "RG") for arm in ("none", "skill") for repeat in range(1, repeats + 1)]


class PairedGainsTest(unittest.TestCase):
    def test_equal_weight_withdrawal_conditions(self):
        trials = trials_for()
        correct = {t.trial_id: t.instruction == "skill" or t.version == "RG" for t in trials}
        gains = paired_gains(trials, correct)
        self.assertEqual(gains["gpt", "R"], [1])
        self.assertEqual(gains["gpt", "RG"], [0])
        self.assertEqual(gains["gpt", "R/RG average"], [0.5])

    def test_incomplete_repeat_excluded_but_completed_failure_counts(self):
        trials = trials_for(repeats=2)
        correct = {t.trial_id: t.instruction == "none" for t in trials}
        del correct["gpt_R_skill_2"]
        gains = paired_gains(trials, correct)
        self.assertNotIn(("gpt", "R"), gains)
        self.assertNotIn(("gpt", "R/RG average"), gains)
        self.assertEqual(gains["gpt", "RG"], [-1])

    def test_models_are_not_pooled(self):
        trials = trials_for() + trials_for("claude")
        correct = {t.trial_id: t.instruction == ("skill" if t.model == "gpt" else "none") for t in trials}
        gains = paired_gains(trials, correct)
        self.assertEqual(gains["gpt", "R/RG average"], [1])
        self.assertEqual(gains["claude", "R/RG average"], [-1])


if __name__ == "__main__":
    unittest.main()
