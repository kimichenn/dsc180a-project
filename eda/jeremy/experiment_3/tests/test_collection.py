import contextlib
import csv
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collection
import planning


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ledger-offline-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "run"
        self.config = json.loads((planning.ROOT / "config.json").read_text())
        self.config.update(models=["fixture-model"], efforts=["none", "medium"])
        self.config["profiles"]["smoke"]["worlds"] = 2
        self.catalog = {"models": [{"model": "fixture-model", "efforts": ["medium"], "visibility": "list"}], "fetched_at": "offline"}
        self.binary = self.root / "fake codex"
        self.binary.write_text(f'#!{sys.executable}\n' + '''
import json, os, pathlib, sys, time
args=sys.argv[1:]
if args == ['login','status']:
 print('Logged in using ChatGPT'); sys.exit(0)
if args == ['--version']:
 print('codex-cli OFFLINE-FIXTURE'); sys.exit(0)
if args == ['exec','--help']:
 print('--json --ephemeral --ignore-user-config --strict-config --output-last-message'); sys.exit(0)
assert args[0] == 'exec'
assert 'forced_login_method="chatgpt"' in args
assert 'agents.enabled=false' in args
assert not any(k in os.environ for k in ('OPENAI_API_KEY','CODEX_API_KEY','CODEX_AUTH_TOKEN'))
assert not list(pathlib.Path(args[args.index('--cd')+1]).iterdir())
assert 'Ledger:' in sys.stdin.read()
mode=os.environ.get('LEDGER_FIXTURE_MODE','ok')
def emit(obj): print(json.dumps(obj),flush=True)
emit({'type':'thread.started','thread_id':'offline-fixture'})
emit({'type':'turn.started'})
if mode == 'timeout': time.sleep(10)
if mode == 'quota':
 emit({'type':'error','message':'usage limit reached'})
 print('OFFLINE FIXTURE usage limit',file=sys.stderr);sys.exit(3)
if mode == 'tool':
 emit({'type':'item.completed','item':{'type':'command_execution','command':'OFFLINE FIXTURE ONLY'}})
answer='not json' if mode == 'malformed' else 'ANSWER: $100K'
pathlib.Path(args[args.index('--output-last-message')+1]).write_text(answer)
emit({'type':'item.completed','item':{'type':'agent_message','text':answer}})
usage={'input_tokens':11,'output_tokens':7,'cached_input_tokens':3,'reasoning_output_tokens':5}
emit({'type':'turn.completed',**({} if mode == 'no_usage' else {'usage':usage})})
''')
        self.binary.chmod(0o700)

    def prepare(self):
        return planning.prepare(self.run, self.config, "smoke", self.catalog)

    def collect(self, limit=2, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return collection.collect(self.run, limit, str(self.binary), **kwargs)

    def csv(self, name):
        with (self.run / name).open() as handle:
            return list(csv.DictReader(handle))

    def test_matrix_never_silently_substitutes_reasoning_off(self):
        manifest = self.prepare()
        self.assertEqual(manifest["planned_trials"], 2)
        self.assertEqual(manifest["unsupported_combinations"][0]["effort"], "none")
        self.assertEqual({t["effort"] for t in planning.read_rows(self.run / "trials.jsonl")}, {"medium"})

    def test_effort_comparisons_pair_only_same_world_and_exclude_failed_attempts(self):
        trials, latest = [], {}
        for world, effort, correct, eligible in (("a", "low", False, True), ("a", "high", True, True),
                                                ("b", "low", True, True), ("b", "high", None, False),
                                                ("c", "high", False, True)):
            identity = world + effort
            trials.append({"trial_id": identity, "world_id": world, "model": "fixture", "effort": effort,
                           "instruction": "none", "records": 2, "context": "RG"})
            latest[identity] = {"correct": correct, "eligible": eligible}
        comparison = collection.paired_summary(trials, latest, "effort")
        self.assertEqual(len(comparison), 1)
        self.assertEqual(comparison[0]["matched_worlds"], 1)
        self.assertEqual(comparison[0]["accuracy_gap_pp"], 100)
        self.assertIsNone(comparison[0]["bootstrap_low_pp"])

    def test_collection_resume_tokens_and_wrong_answer_not_retried(self):
        self.prepare()
        self.assertEqual(self.collect(limit=1), 1)
        first = {str(p): p.read_bytes() for p in (self.run / "attempts").rglob("*") if p.is_file()}
        self.assertEqual(self.collect(limit=2), 1)
        self.assertEqual(self.collect(retry_errors=True), 0)
        for name, contents in first.items():
            self.assertEqual(Path(name).read_bytes(), contents)
        tokens = self.csv("token_usage.csv")
        self.assertEqual(len(tokens), 2)
        self.assertTrue(all(r["input_tokens"] == "11" and r["output_tokens"] == "7" and r["reasoning_output_tokens"] == "5" for r in tokens))
        summaries = self.csv("summary.csv")
        self.assertEqual(sum(int(r["correct_trials"]) for r in summaries), 1)
        self.assertEqual(sum(int(r["eligible_trials"]) for r in summaries), 2)
        self.assertEqual(sum(int(r["all_attempts_output_tokens_known_total"]) for r in summaries), 14)
        self.assertEqual(sum(int(r["all_attempts_reasoning_output_tokens_known_total"]) for r in summaries), 10)
        self.assertEqual({r["outcome"] for r in self.csv("scored.csv")}, {"correct", "wrong_budget"})

    def test_missing_usage_stays_missing_and_empty_accuracy_is_not_zero(self):
        self.prepare()
        collection.analyze(self.run)
        self.assertEqual(self.csv("summary.csv")[0]["accuracy_percent"], "")
        with patch.dict(os.environ, LEDGER_FIXTURE_MODE="no_usage"):
            self.collect(limit=1)
        row = self.csv("token_usage.csv")[0]
        self.assertEqual(row["input_tokens"], "")
        self.assertEqual(row["usage_missing_reason"], "missing_reported_usage")

    def test_tool_events_are_excluded_and_stop_the_batch(self):
        self.prepare()
        with patch.dict(os.environ, LEDGER_FIXTURE_MODE="tool"):
            self.assertEqual(self.collect(), 1)
        row = next(r for r in self.csv("scored.csv") if r["attempt"])
        self.assertEqual(row["outcome"], "excluded_interface")
        self.assertEqual(row["correct"], "")

    def test_malformed_answers_are_errors_not_substring_matches(self):
        self.prepare()
        with patch.dict(os.environ, LEDGER_FIXTURE_MODE="malformed"):
            self.collect()
        self.assertTrue(all(r["outcome"] == "malformed_output" for r in self.csv("scored.csv")))
        self.assertEqual(self.csv("summary.csv")[0]["accuracy_percent"], "0.0")

    def test_quota_stop_explicit_retry_and_attempt_cap(self):
        self.config["profiles"]["smoke"]["worlds"] = 1
        self.config["max_attempts"] = 2
        self.prepare()
        with patch.dict(os.environ, LEDGER_FIXTURE_MODE="quota"):
            self.assertEqual(self.collect(), 1)
            self.assertEqual(self.collect(), 0)
            self.assertEqual(self.collect(retry_errors=True), 1)
            self.assertEqual(self.collect(retry_errors=True), 0)
        self.assertEqual(len(self.csv("token_usage.csv")), 2)
        self.assertTrue(all(r["outcome"] == "rate_limited" for r in self.csv("token_usage.csv")))

    def test_timeout_saves_attempt_and_partial_events(self):
        self.config["timeout_seconds"] = .1
        self.prepare()
        with patch.dict(os.environ, LEDGER_FIXTURE_MODE="timeout"):
            self.assertEqual(self.collect(), 1)
        row = self.csv("token_usage.csv")[0]
        self.assertEqual(row["outcome"], "timeout")
        self.assertTrue((self.run / row["attempt_path"] / "events.jsonl").read_text())
        self.assertFalse((self.run / ".collecting").exists())

    def test_lock_and_changed_frozen_input_prevent_collection(self):
        self.prepare()
        with collection.run_lock(self.run):
            with self.assertRaisesRegex(ValueError, "locked"):
                self.collect()
        prompt = next((self.run / "prompts").iterdir())
        prompt.write_text("edited")
        with self.assertRaisesRegex(ValueError, "Frozen artifact changed"):
            self.collect()

    def test_orphan_attempt_retains_usage_without_claiming_completion(self):
        self.prepare()
        self.collect(limit=1)
        receipt = next((self.run / "attempts").rglob("receipt.json"))
        receipt.unlink()
        collection.analyze(self.run)
        row = self.csv("token_usage.csv")[0]
        self.assertEqual(row["outcome"], "interrupted_before_receipt")
        self.assertEqual(row["input_tokens"], "11")
        self.assertEqual(row["included_in_accuracy"], "False")

    def test_ambiguous_usage_is_not_double_counted(self):
        path = self.root / "events.jsonl"
        path.write_text('\n'.join(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 4}}) for _ in range(2)))
        usage = collection.inspect_events(path)
        self.assertIsNone(usage["input_tokens"])
        self.assertEqual(len(usage["usage_raw"]), 2)

    def test_none_setting_with_positive_reasoning_tokens_is_not_claimed_off(self):
        self.config["efforts"] = ["none"]
        self.catalog["models"][0]["efforts"] = ["none"]
        self.prepare()
        self.collect(limit=1)
        row = next(r for r in self.csv("scored.csv") if r["attempt"])
        self.assertIn("reasoning_off_unverified", row["audit_issues"])

    def test_confirmation_requires_review_and_explicit_estimate_deviation(self):
        with self.assertRaisesRegex(ValueError, "Review development"):
            planning.prepare(self.run, self.config, "confirmation", self.catalog)
        with self.assertRaisesRegex(ValueError, "Exact token matching"):
            planning.prepare(self.run, self.config, "confirmation", self.catalog, development_reviewed=True)


if __name__ == "__main__":
    unittest.main()
