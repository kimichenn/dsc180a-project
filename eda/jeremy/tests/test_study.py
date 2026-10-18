"""Offline checks; all generated test responses live in temporary directories."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import study


class FakeBackend:
    """Test double, never used by the notebook or written into study results."""
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    def runtime(self):
        return {"backend": "TEST_ONLY"}

    def resolve(self, model):
        return {**model, "revision": "0" * 40, "chat_template_sha256": "test"}

    def load(self, model):
        pass

    def close(self):
        pass

    def generate(self, trial):
        self.calls += 1
        if self.fail:
            raise RuntimeError("Intentional test failure")
        return {"status": "ok", "response": f"TEST FIXTURE\nFinal answer: {trial['expected']}"}


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "data").mkdir()
        for name in ("config.json", "skill.md", "data/scenarios.json"):
            shutil.copyfile(ROOT / name, self.root / name)
        self.questions, self.config, self.skill = study.load_study(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def collect(self, backend, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return study.collect(self.root, "pilot", "test", backend=backend, **kwargs)

    def test_question_balance_and_required_calculation(self):
        evaluation = [q for q in self.questions if q["phase"] == "evaluation"]
        self.assertEqual(len(evaluation), 100)
        balance = pd.DataFrame(evaluation).groupby(["subtype", "difficulty"]).size()
        self.assertEqual(balance.tolist(), [25, 25, 25, 25])
        for q in self.questions:
            self.assertNotEqual(study.answer_key(q), study.answer_key(q, misleading=True))
            if q["difficulty"] == "calculation":
                self.assertNotEqual(study.answer_key(q), study.answer_key(q, basic=True))

    def test_expected_trial_counts_and_fixed_prompt_order(self):
        for phase, expected in (("pilot", 40), ("evaluation", 2400)):
            trials = study.build_trials(self.questions, self.config, self.skill, phase)
            self.assertEqual(len(trials), expected)
            self.assertEqual(len({t['trial_id'] for t in trials}), expected)
        for q in self.questions:
            prompts = {c: study.prompt_messages(q, c, self.skill) for c in study.CONDITIONS}
            self.assertEqual(prompts['A'][1], prompts['C'][1])
            self.assertEqual(prompts['B'][1], prompts['D'][1])
            self.assertEqual(prompts['A'][0], prompts['B'][0])
            self.assertEqual(prompts['C'][0], prompts['D'][0])
            clean = prompts['A'][1]['content']
            bad = prompts['B'][1]['content']
            # Exactly one numeric substitution; the authoritative fact stays fixed.
            import difflib
            changes = [x for x in difflib.SequenceMatcher(a=clean, b=bad).get_opcodes() if x[0] != 'equal']
            self.assertTrue(changes)

    def test_final_answer_scoring_rejects_substring_and_negation(self):
        cases = [
            ('Aster is not the answer.', None),
            ('Final answer: Not Aster.', None),
            ('Aster looks plausible.\nFinal answer: Briar', 'matches_misleading'),
            ('**Final answer:** **Aster.**', 'correct'),
            ('Final answer: Aster\nFinal answer: Briar', None),
            ('Final answer: Aster\nActually, Briar.', None),
            ('Final answer: Cannot determine.', 'abstained'),
        ]
        for text, expected_label in cases:
            with self.subTest(text=text):
                self.assertEqual(study.auto_score(text, 'Aster', 'Briar', True)['label'], expected_label)
        self.assertEqual(study.auto_score('Final answer: Briar', 'Aster', 'Briar', False)['label'], 'other_error')
        self.assertIsNone(study.auto_score('Final answer: Aster', 'Aster', 'Briar', True, 'truncated')['label'])

    def test_calculation_error_does_not_claim_misinformation_adoption(self):
        question = next(q for q in self.questions if q["question_id"] == "E41")
        answer = study.answer_key(question, basic=True)
        self.assertEqual(answer, study.answer_key(question, misleading=True))
        response = (
            f"The official register gives {question['entity_a']} {question['correct_value']} "
            f"units and {question['entity_b']} {question['other_value']} units. "
            f"{answer} has the larger stock count.\nFinal answer: {answer}"
        )
        score = study.auto_score(
            response, study.answer_key(question),
            study.answer_key(question, misleading=True), True,
        )
        self.assertEqual(score["label"], "matches_misleading")
        self.assertNotIn("adopted_misleading", study.LABELS)

    def test_loading_uses_dtype_keyword_supported_by_transformers_4_51(self):
        tokenizer = SimpleNamespace(chat_template="frozen template")
        tokenizer_factory = Mock()
        tokenizer_factory.from_pretrained.return_value = tokenizer
        model_factory = Mock()
        transformers = SimpleNamespace(
            AutoTokenizer=tokenizer_factory, AutoModelForCausalLM=model_factory,
        )
        backend = study.LocalQwenBackend.__new__(study.LocalQwenBackend)
        backend.dtype, backend.device = object(), "cpu"
        checkpoint = {
            "model_id": "test/model", "revision": "frozen-revision",
            "chat_template_sha256": study.digest(tokenizer.chat_template),
        }
        with patch.dict(sys.modules, transformers=transformers):
            backend.load(checkpoint)
        model_factory.from_pretrained.assert_called_once_with(
            "test/model", revision="frozen-revision", torch_dtype=backend.dtype,
            device_map="cpu", trust_remote_code=False,
        )
        self.assertIs(backend.model, model_factory.from_pretrained.return_value.eval.return_value)

    def test_no_data_is_missing_not_zero(self):
        frame, config = study.load_results(self.root, 'evaluation', 'empty')
        coverage, paired, accuracy, effects = study.summarize(frame, 3)
        self.assertEqual(coverage['planned'].sum(), 2400)
        self.assertEqual(coverage['scored'].sum(), 0)
        self.assertTrue(accuracy[list(study.CONDITIONS)].isna().all().all())
        self.assertTrue(effects.isna().all().all())
        self.assertTrue(paired.empty)

    def test_complete_repetitions_and_matched_questions_required(self):
        frame, _ = study.load_results(self.root, 'evaluation', 'empty')
        chosen = (frame.question_id == 'E01') & (frame.model == 'qwen3-4b')
        first = frame.index[chosen][0]
        frame.loc[first, ['status', 'label', 'correct']] = ['ok', 'correct', 1]
        self.assertTrue(study.summarize(frame, 3)[1].empty)
        for i in frame.index[chosen]:
            correct = int(frame.loc[i, 'condition'] != 'B')
            frame.loc[i, ['status', 'label', 'correct']] = ['ok', 'correct' if correct else 'matches_misleading', correct]
        coverage, paired, accuracy, effects = study.summarize(frame, 3)
        self.assertEqual(len(paired), 1)
        self.assertEqual(accuracy.loc['qwen3-4b', ['A','B','C','D']].tolist(), [100,0,100,100])
        self.assertEqual(effects.loc['qwen3-4b', 'reduction_in_drop_pp'], 100)
        self.assertTrue(accuracy.loc['qwen3-1.7b', ['A','B','C','D']].isna().all())

    def test_resume_and_freeze(self):
        backend = FakeBackend()
        directory = self.collect(backend, max_new_trials=2)
        self.collect(backend, max_new_trials=2)
        rows = study.read_jsonl(directory / 'responses.jsonl')
        self.assertEqual(len(rows), 4)
        self.assertEqual(len({r['trial_id'] for r in rows}), 4)
        self.assertTrue(all(len(r['checkpoint']['revision']) == 40 for r in rows))
        (self.root / 'skill.md').write_text('A changed skill')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.collect(backend)
        # Analysis still uses the frozen prompts even after the editable skill changes.
        frame, _ = study.load_results(self.root, 'pilot', 'test')
        self.assertEqual(frame.correct.notna().sum(), 4)

    def test_custom_results_root_keeps_collection_and_review_together(self):
        output = self.root / "eda_results"
        backend = FakeBackend()
        directory = self.collect(backend, max_new_trials=2, results_root=output)
        self.collect(backend, max_new_trials=2, results_root=output)
        self.assertEqual(directory, output / "test")
        self.assertFalse((self.root / "runs").exists())
        frame, _ = study.load_results(self.root, "pilot", "test", results_root=output)
        self.assertEqual(frame.correct.notna().sum(), 4)
        self.assertEqual(len(study.read_jsonl(directory / "responses.jsonl")), 4)
        frame.loc[frame.status.eq("ok"), "label"] = None
        queue_path = study.export_review(frame, directory)
        queue = pd.read_csv(queue_path, keep_default_na=False)
        queue.loc[0, "choice"] = "alternative"
        queue.to_csv(queue_path, index=False)
        self.assertEqual(study.apply_review(frame, directory), 1)
        reviewed, _ = study.load_results(self.root, "pilot", "test", results_root=output)
        self.assertEqual((reviewed.label_source == "manual").sum(), 1)
        self.assertEqual(reviewed.loc[reviewed.label_source.eq("manual"), "correct"].iloc[0], 0)
        self.assertFalse((directory / ".collecting").exists())

    def test_failed_attempt_cap_survives_resume(self):
        backend = FakeBackend(fail=True)
        directory = self.collect(backend, max_new_trials=1)
        first_id = study.read_jsonl(directory / 'responses.jsonl')[0]['trial_id']
        self.collect(backend, max_new_trials=1)
        rows = study.read_jsonl(directory / 'responses.jsonl')
        self.assertEqual(sum(r['trial_id'] == first_id for r in rows), 3)
        frame, _ = study.load_results(self.root, 'pilot', 'test')
        self.assertTrue(frame.correct.isna().all())
        self.assertEqual((frame.status == 'error').sum(), 2)

    def test_manual_review_hides_condition_and_preserves_edits(self):
        backend = FakeBackend()
        directory = self.collect(backend, max_new_trials=2)
        frame, _ = study.load_results(self.root, 'pilot', 'test')
        # Force review for a real test completion without modifying its saved raw text.
        completed = frame.status == 'ok'
        frame.loc[completed, 'label'] = None
        path = study.export_review(frame, directory)
        queue = pd.read_csv(path, keep_default_na=False)
        self.assertNotIn('model', queue.columns)
        self.assertNotIn('condition', queue.columns)
        queue.loc[0, 'choice'] = 'expected'
        queue.loc[0, 'notes'] = 'Reviewed fixture'
        queue.to_csv(path, index=False)
        study.export_review(frame, directory)
        self.assertEqual(pd.read_csv(path).loc[0, 'choice'], 'expected')
        self.assertEqual(study.apply_review(frame, directory), 1)
        rescored, _ = study.load_results(self.root, 'pilot', 'test')
        self.assertEqual((rescored.label_source == 'manual').sum(), 1)

    def test_legacy_manual_label_is_normalized_without_rewriting_history(self):
        trial = next(t for t in study.build_trials(
            self.questions, self.config, self.skill, "pilot",
        ) if t["condition"] == "B")
        directory = self.root / "legacy_review"
        directory.mkdir()
        response = {**trial, "status": "ok", "response": "Ambiguous response requiring review."}
        study.append_jsonl(directory / "responses.jsonl", response)
        label_path = directory / "manual_labels.jsonl"
        study.append_jsonl(label_path, {
            "review_id": study.response_id(response), "label": "adopted_misleading",
            "notes": "Historical review", "labeled_at": "2025-01-01T00:00:00+00:00",
        })
        original_history = label_path.read_bytes()
        reviewed = study.result_frame([trial], directory).iloc[0]
        self.assertEqual(reviewed["label"], "matches_misleading")
        self.assertEqual(reviewed["label_source"], "manual")
        self.assertEqual(reviewed["correct"], 0)
        self.assertEqual(label_path.read_bytes(), original_history)

    def test_manual_alternative_uses_descriptive_label_only_under_misleading(self):
        trials = study.build_trials(self.questions, self.config, self.skill, "pilot")
        trials = [next(t for t in trials if t["condition"] == c) for c in ("A", "B")]
        directory = self.root / "new_review"
        directory.mkdir()
        for trial in trials:
            study.append_jsonl(directory / "responses.jsonl", {
                **trial, "status": "ok", "response": "Ambiguous response requiring review.",
            })
        frame = study.result_frame(trials, directory)
        queue_path = study.export_review(frame, directory)
        queue = pd.read_csv(queue_path, keep_default_na=False)
        queue["choice"] = "alternative"
        queue.to_csv(queue_path, index=False)
        self.assertEqual(study.apply_review(frame, directory), 2)
        reviewed = study.result_frame(trials, directory).set_index("condition")
        self.assertEqual(reviewed.loc["A", "label"], "other_error")
        self.assertEqual(reviewed.loc["B", "label"], "matches_misleading")
        stored_labels = {r["label"] for r in study.read_jsonl(directory / "manual_labels.jsonl")}
        self.assertEqual(stored_labels, {"other_error", "matches_misleading"})

    def test_evaluation_requires_pilot_review(self):
        with self.assertRaisesRegex(ValueError, 'pilot'):
            study.collect(self.root, 'evaluation', 'test', backend=FakeBackend())

    def test_run_lock(self):
        directory = study.run_path(self.root, 'test')
        directory.mkdir(parents=True)
        with study.run_lock(directory):
            with self.assertRaises(RuntimeError):
                with study.run_lock(directory):
                    pass
        self.assertFalse((directory / '.collecting').exists())

    def test_empty_exports_do_not_claim_accuracy(self):
        frame, _ = study.load_results(self.root, 'pilot', 'empty')
        directory = study.export_results(frame, 1, self.root / 'exports')
        text = (directory / 'findings.md').read_text()
        self.assertIn('Collected responses: 0/40', text)
        self.assertIn('incomplete', text)
        self.assertIn('this label does not establish adoption of misinformation', text)
        self.assertIn('lower clean-with-skill accuracy alone', text)


if __name__ == '__main__':
    unittest.main()
