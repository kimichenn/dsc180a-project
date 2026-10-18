"""Execute notebook analysis on CPU-only fixtures without model calls or exports."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import study


class NotebookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "data").mkdir()
        for name in ("study.py", "config.json", "skill.md", "data/scenarios.json"):
            shutil.copyfile(ROOT / name, self.root / name)
        self.notebook = json.loads((ROOT / "eda.ipynb").read_text())

    def tearDown(self):
        plt.close("all")
        self.temporary.cleanup()

    def execute_notebook(self):
        torch = types.ModuleType("torch")
        torch.cuda = Mock()
        torch.cuda.is_available.return_value = False
        torch.cuda.get_device_name.side_effect = AssertionError("CUDA device lookup on a CPU-only host")
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        namespace = {"__name__": "__main__"}
        output = io.StringIO()
        with (
            patch.dict(sys.modules, {"torch": torch}),
            patch.object(sys, "path", sys.path.copy()),
            patch("pathlib.Path.cwd", return_value=self.root),
            patch("importlib.reload", side_effect=lambda module: module),
            patch("IPython.display.display"),
            patch.object(plt, "show"),
            patch.object(study, "collect", side_effect=AssertionError("Unexpected collection")) as collect,
            patch.object(study, "export_results", side_effect=AssertionError("Unexpected export")),
            patch.object(study, "export_review", side_effect=AssertionError("Unexpected review export")),
            patch.object(study, "apply_review", side_effect=AssertionError("Unexpected review import")),
            matplotlib.rc_context(),
            pd.option_context("display.max_colwidth", 50),
            contextlib.redirect_stdout(output),
        ):
            for index, cell in enumerate(self.notebook["cells"]):
                if cell["cell_type"] == "code":
                    exec(compile("".join(cell["source"]), f"eda.ipynb:cell_{index}", "exec"), namespace)
        collect.assert_not_called()
        torch.cuda.get_device_name.assert_not_called()
        self.assertFalse(namespace["RUN_COLLECTION"])
        self.assertEqual(
            before,
            {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()},
        )
        return namespace, output.getvalue()

    def test_run_all_defaults_on_cpu_never_collect_or_clip_expanded_dataset(self):
        namespace, output = self.execute_notebook()
        self.assertEqual(namespace["ROOT"], self.root)
        self.assertEqual(len(namespace["questions"]), 105)
        self.assertEqual(namespace["balance"].to_numpy().tolist(), [[25, 25], [25, 25]])
        self.assertGreater(namespace["axes"][0].get_ylim()[1], 25)
        self.assertEqual(len(namespace["plan"]), 40)
        self.assertTrue(namespace["results"].status.eq("not_collected").all())
        self.assertIn("Evaluation: 100 × 4 × 2 × 3 = 2400", output)
        self.assertFalse((self.root / "runs").exists())

    def test_frozen_questions_models_counts_and_trial_prompt_survive_edited_inputs(self):
        questions, config, skill = study.load_study(self.root)
        questions = [q for q in questions if q["phase"] == "pilot"] + [
            q for q in questions if q["phase"] == "evaluation"
        ][:20]
        config["models"] = {"legacy-model": config["models"]["qwen3-4b"]}
        skill = "Frozen fixture skill"
        trials = study.build_trials(questions, config, skill, "pilot")
        frozen_prompt = "Frozen fixture prompt, preserved verbatim."
        for trial in trials:
            if trial["question_id"] == "P03" and trial["condition"] == "D":
                trial["messages"][1]["content"] = frozen_prompt
        design = {"phase": "pilot", "questions": questions, "config": config,
                  "skill": skill, "trials": trials}
        directory = self.root / "runs" / "pilot_v1"
        directory.mkdir(parents=True)
        (directory / "manifest.json").write_text(json.dumps({"design": design}))
        # Frozen analysis must not depend on mutable inputs even being valid.
        (self.root / "config.json").write_text("edited, invalid current config")
        (self.root / "data/scenarios.json").write_text("edited, invalid current questions")
        (self.root / "skill.md").write_text("Edited current skill")

        namespace, output = self.execute_notebook()
        self.assertEqual(len(namespace["questions"]), 25)
        self.assertEqual(list(namespace["config"]["models"]), ["legacy-model"])
        self.assertEqual(namespace["skill"], skill)
        self.assertEqual(len(namespace["plan"]), 20)
        self.assertEqual(namespace["preview_messages"]["D"][1]["content"], frozen_prompt)
        self.assertIn("Evaluation: 20 × 4 × 1 × 3 = 240", output)
        self.assertIn("Design: frozen run", output)
        self.assertIn(frozen_prompt, output)


if __name__ == "__main__":
    unittest.main()
