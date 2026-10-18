"""Exercise terminal exports in temporary folders, without downloading models."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import study
import eda
from test_study import FakeBackend


class MixedBackend(FakeBackend):
    def generate(self, trial):
        answer = trial["alternative"] if trial["condition"] == "B" else trial["expected"]
        return {"status": "ok", "response": f"TEST FIXTURE\nFinal answer: {answer}"}


class ScriptTests(unittest.TestCase):
    def copy_frozen_manifest(self, folder):
        directory = folder / "outputs" / "pilot_v1"
        directory.mkdir(parents=True)
        raw = (ROOT / "runs" / "pilot_v1" / "manifest.json").read_bytes()
        (directory / "manifest.json").write_bytes(raw)
        return directory, raw, json.loads(raw)["design"]

    def assert_frozen_exports(self, directory, raw, design):
        questions = pd.read_csv(directory / "questions.csv")
        expected_questions = pd.DataFrame(design["questions"])
        pd.testing.assert_frame_equal(
            questions[expected_questions.columns], expected_questions,
        )
        models = pd.read_csv(directory / "models.csv", index_col=0)
        pd.testing.assert_frame_equal(models, pd.DataFrame(design["config"]["models"]).T)
        accuracy = pd.read_csv(directory / "accuracy.csv", index_col=0)
        self.assertEqual(set(accuracy.index), set(models.index))
        self.assertTrue(accuracy[list(study.CONDITIONS)].isna().all().all())
        scored = pd.read_csv(directory / "scored.csv")
        self.assertEqual(set(scored.trial_id), {trial["trial_id"] for trial in design["trials"]})
        self.assertTrue(scored.status.eq("not_collected").all())
        preview = (directory / "prompt_preview.txt").read_text()
        self.assertIn(design["skill"], preview)
        trial = next(t for t in design["trials"] if t["question_id"] == "P03" and t["condition"] == "D")
        for message in trial["messages"]:
            self.assertIn(message["content"], preview)
        self.assertEqual((directory / "manifest.json").read_bytes(), raw)
        self.assertFalse((directory / "responses.jsonl").exists())

    def run_script(self, folder, *args):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "eda.py"), "--results-dir", str(folder / "outputs"), *args],
            cwd=folder, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return folder / "outputs" / "pilot_v1"

    def test_preview_exports_from_another_working_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            directory = self.run_script(folder)
            scored = pd.read_csv(directory / "scored.csv")
            self.assertEqual(len(scored), 40)
            self.assertTrue(scored.status.eq("not_collected").all())
            self.assertTrue(pd.read_csv(directory / "accuracy.csv")[list(study.CONDITIONS)].isna().all().all())
            self.assertFalse((directory / "responses.jsonl").exists())
            self.assertFalse((directory / "manifest.json").exists())
            self.assertEqual(len(pd.read_csv(directory / "questions.csv")), 105)
            for name in ("dataset_overview", "collection_progress"):
                self.assertGreater((directory / "plots" / f"{name}.png").stat().st_size, 1000)
            self.assertFalse((directory / "plots" / "accuracy.png").exists())
            self.assertIn("Prompt preview:", (directory / "prompt_preview.txt").read_text())

    def test_frozen_run_exports_use_the_original_design(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            directory, raw, design = self.copy_frozen_manifest(folder)
            self.run_script(folder)
            self.assert_frozen_exports(directory, raw, design)

    def test_frozen_run_exports_work_without_current_study_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            directory, raw, design = self.copy_frozen_manifest(folder)
            source = folder / "missing_study_inputs"
            source.mkdir()
            with (
                patch.object(eda, "ROOT", source),
                patch.object(study, "prompt_messages", side_effect=AssertionError("Frozen prompts must not be rebuilt")),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                eda.main(["--results-dir", str(folder / "outputs")])
            self.assert_frozen_exports(directory, raw, design)

    def test_evaluation_preview_and_dataset_plot(self):
        from matplotlib.figure import Figure

        plots = []
        savefig = Figure.savefig

        def check_and_save(figure, filename, *args, **kwargs):
            if Path(filename).name == "dataset_overview.png":
                axis = figure.axes[0]
                heights = [bar.get_height() for bar in axis.patches]
                self.assertEqual(heights, [25, 25, 25, 25])
                self.assertGreaterEqual(axis.get_ylim()[1], max(heights))
                plots.append(filename)
            return savefig(figure, filename, *args, **kwargs)

        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(Figure, "savefig", check_and_save), contextlib.redirect_stdout(io.StringIO()):
                eda.main(["--results-dir", temporary, "--phase", "evaluation"])
            directory = Path(temporary) / "evaluation_v1"
            scored = pd.read_csv(directory / "scored.csv")
            self.assertEqual(len(scored), 2400)
            self.assertTrue(scored.status.eq("not_collected").all())
            self.assertTrue(pd.read_csv(directory / "accuracy.csv")[list(study.CONDITIONS)].isna().all().all())
            e01 = scored.loc[scored.question_id.eq("E01"), "question"].iloc[0]
            self.assertIn(e01, (directory / "prompt_preview.txt").read_text())
            self.assertFalse((directory / "responses.jsonl").exists())
            self.assertFalse((directory / "manifest.json").exists())
        self.assertEqual(len(plots), 1)

    def test_scored_exports_and_review_refresh(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with contextlib.redirect_stdout(io.StringIO()):
                study.collect(ROOT, "pilot", "pilot_v1", backend=MixedBackend(),
                              results_root=folder / "outputs")
            raw = (folder / "outputs" / "pilot_v1" / "responses.jsonl").read_bytes()
            directory = self.run_script(folder)
            accuracy = pd.read_csv(directory / "accuracy.csv")
            self.assertEqual(accuracy["B"].tolist(), [0, 0])
            self.assertEqual(accuracy["D"].tolist(), [100, 100])
            for name in ("accuracy", "question_changes", "error_types"):
                self.assertGreater((directory / "plots" / f"{name}.png").stat().st_size, 1000)
            self.assertEqual(len(pd.read_csv(directory / "category_summary.csv")), 8)
            queue = pd.read_csv(directory / "review_queue.csv", keep_default_na=False)
            queue["choice"] = "expected"
            queue.to_csv(directory / "review_queue.csv", index=False)
            self.run_script(folder, "--import-review")
            self.assertEqual(pd.read_csv(directory / "accuracy.csv")["B"].tolist(), [100, 100])
            self.assertFalse((directory / "plots" / "error_types.png").exists())
            self.assertFalse((directory / "error_counts.csv").exists())
            self.assertEqual((directory / "responses.jsonl").read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
