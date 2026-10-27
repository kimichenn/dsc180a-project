import hashlib
import tempfile
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from experiment.config import GeneratorSettings, load_config
from experiment.prompts import INSTRUCTIONS
from experiment.runs import load, prepare, schedule, verify_collection_source
from experiment.scoring import MISTAKES
from experiment.screen_report import screen_snapshot
from scripts.run_skill_screen import validate_design


class MinimalPilotTest(unittest.TestCase):
    config_path = Path('config/minimal_checklist_v3_pilot.toml')

    def test_fresh_balanced_ten_repeat_design_and_old_draft_preserved(self):
        config = load_config(self.config_path)
        worlds = [SimpleNamespace(world_id=str(seed)) for seed in config.seeds]
        trials = schedule(config, worlds)
        self.assertEqual(validate_design(config, self.config_path), 400)
        self.assertEqual(len(trials),400)
        self.assertEqual(len({t.trial_id for t in trials}),400)
        self.assertEqual(Counter(t.instruction for t in trials),{'none':200,'minimal_v3':200})
        self.assertEqual(set(Counter((t.world_id,t.version,t.instruction) for t in trials).values()),{10})
        self.assertEqual(set(Counter(t.world_id for t in trials).values()),{80})
        previous = load_config(Path('config/skill_drafts_pilot.toml'))
        self.assertFalse(set(config.seeds) & set(previous.seeds))
        self.assertEqual(hashlib.sha256(INSTRUCTIONS['minimal_v2'].encode()).hexdigest(),
                         previous.frozen_instruction_sha256['minimal_v2'])

    def test_launcher_refuses_unintended_scale_model_or_configuration(self):
        config = load_config(self.config_path)
        with self.assertRaisesRegex(ValueError,'authorized 400-call'):
            validate_design(replace(config,logs=30),self.config_path)
        with self.assertRaisesRegex(ValueError,'GPT-6 Astra at low'):
            validate_design(replace(config,models={'gpt':replace(config.models['gpt'],effort='high')}),self.config_path)
        with self.assertRaisesRegex(ValueError,'Unrecognized'):
            validate_design(config,Path('unknown.toml'))

    def test_new_body_is_frozen_without_altering_original_run(self):
        config = replace(load_config(self.config_path),logs=1,repeats=1,
                         generator=GeneratorSettings(records=40,chronological=True,max_attempts=500))
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run'
            with patch.dict(INSTRUCTIONS,minimal_v3='changed'):
                with self.assertRaisesRegex(ValueError,'instruction minimal_v3 differs'):
                    prepare(config,self.config_path,folder,'test')
            run=prepare(config,self.config_path,folder,'test')
            self.assertEqual(len(load(folder).trials),8)
            verify_collection_source(run)
            self.assertTrue((folder/'source/experiment/skills/conflict-resolution-minimal-v3/SKILL.md').exists())

    def test_two_arm_report_keeps_incomplete_logs_out_of_comparison(self):
        config=replace(load_config(self.config_path),logs=2,repeats=2)
        trials=schedule(config,[SimpleNamespace(world_id='a'),SimpleNamespace(world_id='b')])
        attempts=[]
        for t in trials:
            if t.world_id=='b':
                continue
            correct=t.instruction=='minimal_v3' or t.version in ('C','E') or t.repeat==1
            attempts.append(dict(trial_id=t.trial_id,status='completed',eligible=True,
                started_at='2026-10-26T00:00:00+00:00',usage={},
                response='ANSWER: $100K' if correct else 'ANSWER: $101K'))
        run=SimpleNamespace(config=config,trials=trials,
            keys={w:{'answer':100,'buckets':{k:[] for k in MISTAKES}} for w in ('a','b')})
        with patch('experiment.screen_report.read_attempts',return_value=attempts):
            summary,_=screen_snapshot(run)
        self.assertEqual(summary['collected'],16)
        self.assertEqual(summary['complete_logs'],{'gpt':1})
        revised=next(r for r in summary['metrics'] if r['instruction']=='minimal_v3')
        self.assertEqual(revised['conflict_gain_pp'],50)
        self.assertEqual(revised['clean_explicit_gain_pp'],0)
        self.assertEqual(revised['per_log_conflict_gain_pp'],[50])


if __name__=='__main__':
    unittest.main()
