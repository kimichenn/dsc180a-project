import tempfile
import unittest
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from experiment.checks import check_chronological_range, check_world
from experiment.config import GeneratorSettings, RepeatabilitySettings, config_from_dict, config_to_dict, load_config
from experiment.generator import generate
from experiment.records import FINANCE, Record
from experiment.repeat_report import agreement, complete_main_cells, holm, repeat_report, sign_flip_p
from experiment.scoring import MISTAKES
from experiment.runs import Trial, load, prepare, schedule
from experiment.solvers import replay, solve_backward


class RepeatStudyTest(unittest.TestCase):
    def test_chronology_checks_intermediate_canceled_change(self):
        records = [Record(1,'opening',FINANCE,500), Record(2,'adjust',FINANCE,-400),
                   Record(3,'withdraw',FINANCE,target=2)]
        self.assertEqual(solve_backward(records),500)
        self.assertTrue(check_chronological_range(records,GeneratorSettings()))

    def test_nested_withdrawal_restores_exact_signed_effect(self):
        records = [Record(1,'opening',FINANCE,500),Record(2,'adjust',FINANCE,-100),
                   Record(3,'withdraw',FINANCE,target=2),Record(4,'withdraw',FINANCE,target=3)]
        self.assertEqual([d for _,d in replay(records)],[500,-100,100,-100])
        self.assertFalse(check_chronological_range(records,GeneratorSettings()))

    def test_generated_worlds_are_valid_and_reproducible(self):
        settings=GeneratorSettings(records=40,chronological=True,max_attempts=500)
        for seed in range(1,6):
            world=generate(seed,settings)
            self.assertEqual(check_world(world,settings),[])
            self.assertEqual(world.to_json(),generate(seed,settings).to_json())

    def test_uniform_schedule_has_2400_calls_and_identical_repeat_inputs(self):
        config=load_config(Path('config/skill_repeat_10x.toml'))
        worlds=[SimpleNamespace(world_id=f's{seed}_n1600') for seed in config.seeds]
        trials=schedule(config,worlds)
        self.assertEqual(len(trials),2400)
        self.assertEqual(len({t.trial_id for t in trials}),2400)
        counts=Counter((t.world_id,t.version,t.instruction,t.model) for t in trials)
        self.assertEqual(set(counts.values()),{10})
        self.assertEqual(Counter(t.world_id for t in trials),{w.world_id:80 for w in worlds})
        self.assertEqual(trials,schedule(config,worlds))
        self.assertEqual(len({(t.prompt_file,t.system_file) for t in trials}),240)
        self.assertEqual(config,config_from_dict(json.loads(json.dumps(config_to_dict(config)))))

    def test_original_two_tier_schedule_has_720_plus_280(self):
        config=load_config(Path('config/skill_repeat_v2.toml'))
        worlds=[SimpleNamespace(world_id=str(seed)) for seed in config.seeds]
        trials=schedule(config,worlds)
        self.assertEqual(sum(t.repeat<=3 for t in trials),720)
        extra=[t for t in trials if t.repeat>3]
        self.assertEqual(len(extra),280)
        self.assertEqual(len({t.world_id for t in extra}),10)
        self.assertEqual({t.version for t in extra},{'R','RG'})

    def test_complete_logs_required_and_failures_count(self):
        trials=[Trial(str(i),i,'w','R','skill','gpt',i+1) for i in range(10)]
        results={str(i):{'correct':False} for i in range(9)}
        self.assertEqual(complete_main_cells(trials,results,10),({},set()))
        results['9']={'correct':False}
        cells,complete=complete_main_cells(trials,results,10)
        self.assertEqual(complete,{('gpt','w')})
        self.assertEqual(len(cells['gpt','w','skill','R']),10)

    def test_missing_answers_never_agree(self):
        self.assertEqual(agreement([None,None,100,100]),1/6)
        self.assertEqual(agreement([200]*10),1)
        self.assertEqual(agreement([100,200]),0)

    def test_exact_sign_flip_and_multiple_tests(self):
        self.assertEqual(sign_flip_p([1]*5),2/32)
        self.assertEqual(sign_flip_p([0]*30),1)
        self.assertEqual(sign_flip_p([1,-1]),1)
        self.assertEqual(holm([.01,.04]),[.02,.04])

    def test_skill_hash_guard_and_frozen_file_tampering(self):
        config=replace(load_config(Path('config/skill_repeat_10x.toml')),logs=1,
                       generator=GeneratorSettings(records=40,chronological=True),repeats=1)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run'
            with self.assertRaisesRegex(ValueError,'skill text differs'):
                prepare(replace(config,frozen_skill_sha256='bad'),Path('config/skill_repeat_10x.toml'),folder,'test')
            run=prepare(config,Path('config/skill_repeat_10x.toml'),folder,'test')
            self.assertEqual(len(load(folder).trials),8)
            (folder/'system/skill.txt').write_text('changed')
            with self.assertRaisesRegex(ValueError,'frozen files changed'):
                load(folder)

    def test_full_report_averages_repeats_and_records_variability(self):
        config=replace(load_config(Path('config/skill_repeat_10x.toml')),logs=1)
        trials=schedule(config,[SimpleNamespace(world_id='w')])
        attempts=[dict(trial_id=t.trial_id,status='completed',eligible=True,
                       started_at='2026-10-25T00:00:00+00:00',usage={},
                       response='ANSWER: $101K' if t.version=='R' and t.instruction=='none' else 'ANSWER: $100K')
                  for t in trials]
        with tempfile.TemporaryDirectory() as tmp:
            run=SimpleNamespace(path=Path(tmp),config=config,trials=trials,
                                keys={'w':{'answer':100,'buckets':{k:[] for k in MISTAKES}}})
            with patch('experiment.repeat_report.read_attempts',return_value=attempts):
                report=repeat_report(run)
            self.assertIn('80/80 eligible',report)
            self.assertIn('1/1 complete base logs',report)
            self.assertIn('averaged over R and RG: +50.0 pp',report)
            self.assertTrue((run.path/'analysis/repeat_variability.csv').exists())


if __name__=='__main__':
    unittest.main()
