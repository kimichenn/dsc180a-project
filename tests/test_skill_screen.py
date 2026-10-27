import hashlib
import json
import shutil
import tempfile
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from experiment.config import GeneratorSettings, config_from_dict, config_to_dict, load_config
from experiment.prompts import INSTRUCTIONS, SKILL
from experiment.pilot import pilot_report
from experiment.repeat_report import repeat_report
from experiment.runs import load, prepare, schedule, verify_collection_source
from experiment.scoring import MISTAKES
from experiment.screen_report import screen_report, screen_snapshot


class SkillScreenTest(unittest.TestCase):
    def config(self):
        return load_config(Path('config/skill_drafts_pilot.toml'))

    def test_balanced_schedule_and_frozen_drafts(self):
        config = self.config()
        trials = schedule(config, [SimpleNamespace(world_id=str(seed)) for seed in config.seeds])
        self.assertEqual(len(trials), 360)
        self.assertEqual(len({t.trial_id for t in trials}), 360)
        self.assertEqual(set(Counter((t.world_id,t.version,t.instruction) for t in trials).values()), {5})
        self.assertEqual(set(Counter(t.instruction for t in trials).values()), {60})
        self.assertEqual(config, config_from_dict(json.loads(json.dumps(config_to_dict(config)))))
        self.assertEqual(hashlib.sha256(SKILL.encode()).hexdigest(),
                         '110dc3202c110644d473c29e0d5bfff26ca008eecc7e0a8b2930a91c8eda946a')
        for arm, digest in config.frozen_instruction_sha256.items():
            self.assertEqual(hashlib.sha256(INSTRUCTIONS[arm].encode()).hexdigest(), digest)

    def test_two_arm_reports_reject_multi_arm_design(self):
        run=SimpleNamespace(config=self.config())
        for report in (pilot_report, repeat_report):
            with self.assertRaisesRegex(ValueError, 'use screen-report'):
                report(run)

    def test_draft_tampering_and_markdown_source_freeze(self):
        config = replace(self.config(), logs=1, repeats=1,
                         generator=GeneratorSettings(records=40,chronological=True))
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)/'run'
            with patch.dict(INSTRUCTIONS, ledger_v2='changed'):
                with self.assertRaisesRegex(ValueError, 'instruction ledger_v2 differs'):
                    prepare(config,Path('config/skill_drafts_pilot.toml'),folder,'test')
            run = prepare(config,Path('config/skill_drafts_pilot.toml'),folder,'test')
            self.assertEqual(len(load(folder).trials),24)
            verify_collection_source(run)
            shadow = Path(temp)/'shadow'
            shutil.copytree(folder/'source', shadow)
            with patch('experiment.runs.REPO_ROOT', shadow):
                verify_collection_source(run)
                (shadow/'experiment/skills/conflict-resolution-ledger/SKILL.md').write_text('changed')
                with self.assertRaisesRegex(ValueError, 'collection source changed'):
                    verify_collection_source(run)

    def test_multi_arm_report_is_paired_and_missing_is_not_failure(self):
        config = replace(self.config(), logs=2, repeats=2)
        trials = schedule(config, [SimpleNamespace(world_id='w1'),SimpleNamespace(world_id='w2')])
        attempts = []
        for t in trials:
            if t.world_id == 'w2':
                continue
            answer = 'ANSWER: $100K'
            if t.instruction == 'none' and t.version in ('R','RG'):
                answer = 'ANSWER: $101K'
            if t.instruction == 'minimal_v2' and t.version == 'C':
                answer = 'Unable to determine.'
            attempts.append(dict(trial_id=t.trial_id,status='completed',eligible=True,
                started_at='2026-10-25T00:00:00+00:00',usage={'output_tokens':100},response=answer))
        keys={w:{'answer':100,'buckets':{k:[] for k in MISTAKES}} for w in ('w1','w2')}
        with tempfile.TemporaryDirectory() as temp:
            run=SimpleNamespace(path=Path(temp),config=config,trials=trials,keys=keys)
            with patch('experiment.screen_report.read_attempts',return_value=attempts):
                result, scored=screen_snapshot(run)
                report=screen_report(run)
            self.assertEqual(result['collected'],48)
            self.assertEqual(result['complete_logs'],{'gpt':1})
            rows={r['instruction']:r for r in result['metrics']}
            self.assertEqual(rows['ledger_v2']['conflict_gain_pp'],100)
            self.assertEqual(rows['none']['conflict_gain_pp'],0)
            self.assertEqual(rows['minimal_v2']['clean_explicit_gain_pp'],-50)
            self.assertEqual(rows['minimal_v2']['mean_answer_agreement'],.75)
            self.assertIn('1/2 complete logs', report)
            # Even one absent response excludes that log for every arm equally.
            with patch('experiment.screen_report.read_attempts',return_value=attempts[:-1]):
                result,_=screen_snapshot(run)
            self.assertEqual(result['metrics'],[])


if __name__ == '__main__':
    unittest.main()
