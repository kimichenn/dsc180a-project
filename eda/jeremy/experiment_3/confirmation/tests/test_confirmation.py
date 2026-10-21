import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collection
import input_matching
import ledger
import planning


class TokenMatchingTests(unittest.TestCase):
    def test_real_tokens_match_and_keep_records_question_and_answers_unchanged(self):
        counter = ledger.TokenCounter({"kind": "tiktoken", "encoding": "o200k_base"})
        world = ledger.generate(400000)
        texts = {c: ledger.render(rows) for c, rows in world["contexts"].items()}
        matched, counts = ledger.match_texts(texts, counter, .001, before=ledger.QUESTION)
        self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)
        for c in texts:
            self.assertEqual(texts[c].split("End of ledger.")[0], matched[c].split("End of ledger.")[0])
            self.assertEqual(texts[c].split(ledger.QUESTION)[1], matched[c].split(ledger.QUESTION)[1])
            self.assertEqual(ledger.solve(world["contexts"][c])[0], world["expected"])
        again, _ = ledger.match_texts(texts, counter, .001, before=ledger.QUESTION)
        self.assertEqual(matched, again)

    def test_character_matching_regression_is_visible_to_tokenizer(self):
        world = ledger.generate(300000)
        texts = {c: ledger.render(rows) for c, rows in world["contexts"].items()}
        characters = ledger.TokenCounter({"kind": "characters", "characters_per_token": 4})
        token_counter = ledger.TokenCounter({"kind": "tiktoken", "encoding": "o200k_base"})
        old_style, _ = ledger.match_texts(texts, characters, before=ledger.QUESTION)
        counts = [token_counter.count(old_style[c]) for c in ['C','RG']]
        self.assertGreater((max(counts)-min(counts))/max(counts), .10)

    def test_cannot_claim_exact_model_tokenization_from_configuration(self):
        c = ledger.TokenCounter({"kind": "tiktoken", "encoding": "o200k_base", "verified_for_models": ["gpt-6-astra"]})
        self.assertFalse(c.exact_for("gpt-6-astra"))

    def test_missing_or_duplicated_question_boundary_rejected(self):
        c = ledger.TokenCounter({"kind": "characters", "characters_per_token": 4})
        for text in ['absent', ledger.QUESTION*2]:
            with self.assertRaises(ValueError):
                ledger.match_texts({'C':text}, c, before=ledger.QUESTION)


class ConfirmationCollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='confirmation-offline-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root/'run'
        self.config = json.loads((planning.ROOT/'config.json').read_text())
        self.config['profiles']['confirmation'].update(worlds=2, record_counts=[40])
        self.catalog = {'models':[{'model':'gpt-6-astra','efforts':['high']}], 'fetched_at':'offline'}
        self.runtime = {'cli_version':'OFFLINE-FIXTURE'}
        report = json.loads((planning.ROOT/'tokenizer_calibration.json').read_text())
        report['runtime'] = self.runtime
        self.evidence = self.root/'evidence.json'
        planning.dump(self.evidence,report)
        self.config['tokenizer_calibration'] = {'path':str(self.evidence), 'sha256':planning.digest(self.evidence)}
        runtime_path=self.root/'runtime.json'
        planning.dump(runtime_path,self.runtime)
        self.config['collection_runtime']={'path':str(runtime_path),'sha256':planning.digest(runtime_path)}

    def prepare(self):
        return planning.prepare(self.run,self.config,'confirmation',self.catalog,
                                allow_estimated_tokens=True,development_reviewed=True)

    def execute(self, mode):
        def fake(run, trial, number, runtime, timeout):
            folder=run/'attempts'/trial['trial_id']/f'{number:03d}'
            folder.mkdir(parents=True)
            start={'trial_id':trial['trial_id'],'attempt':number}
            planning.dump(folder/'started.json',start)
            value=None if mode=='missing' else (2000 if mode=='mismatch' and trial['context']=='RG' else 1000)
            response='ANSWER: ABSTAIN'
            events=[{'type':'thread.started'},{'type':'turn.started'},
                    {'type':'item.completed','item':{'type':'agent_message','text':response}},
                    {'type':'turn.completed','usage':{'input_tokens':value,'output_tokens':11}}]
            (folder/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
            (folder/'response.txt').write_text(response)
            receipt={**start,'execution_status':'completed','returncode':0,'elapsed_seconds':1,
                     'response':response,'stderr_tail':'','events':collection.inspect_events(folder/'events.jsonl')}
            planning.dump(folder/'receipt.json',receipt)
            return receipt
        return fake

    def collect(self,mode='matched',limit=4):
        with patch.object(collection,'preflight',return_value=self.runtime), patch.object(collection,'execute_attempt',side_effect=self.execute(mode)):
            return collection.collect(self.run,limit)

    def test_pair_order_freshness_and_frozen_calibration(self):
        self.prepare()
        manifest,trials,worlds=planning.load_plan(self.run,check_sources=True)
        self.assertEqual(len(trials),4)
        self.assertEqual({w['seed'] for w in worlds.values()},{400000,400001})
        for i in [0,2]:
            self.assertEqual(trials[i]['world_id'],trials[i+1]['world_id'])
            self.assertEqual({trials[i]['context'],trials[i+1]['context']},{'C','RG'})
        self.assertIn('tokenizer_calibration.json',manifest['artifact_hashes'])
        (self.run/'tokenizer_calibration.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'Frozen artifact'):
            planning.load_plan(self.run)

    def test_reported_mismatch_stops_after_pair_and_blocks_resume(self):
        self.prepare()
        self.assertEqual(self.collect('mismatch'),2)
        p=json.loads((self.run/'progress.json').read_text())
        self.assertEqual(p['input_matching']['status'],'failed')
        self.assertEqual(p['outcomes'],{'abstained':2})
        with self.assertRaisesRegex(ValueError,'matching failed'):
            self.collect()

    def test_missing_usage_stops_immediately_without_relabeling_response(self):
        self.prepare()
        self.assertEqual(self.collect('missing'),1)
        p=json.loads((self.run/'progress.json').read_text())
        self.assertEqual(p['input_matching']['failed_pairs'],1)
        self.assertEqual(p['outcomes'],{'abstained':1})

    def test_all_abstentions_still_complete_when_lengths_match_and_resume_is_safe(self):
        self.prepare()
        self.assertEqual(self.collect(limit=1),1)
        self.assertEqual(self.collect(),3)
        self.assertEqual(self.collect(),0)
        p=json.loads((self.run/'progress.json').read_text())
        self.assertEqual(p['input_matching']['matched_pairs'],2)
        self.assertEqual(p['input_matching']['status'],'passed')
        self.assertEqual(p['outcomes'],{'abstained':4})

    def test_runtime_change_blocks_requests(self):
        self.prepare()
        with patch.object(collection,'preflight',return_value={'cli_version':'CHANGED'}), patch.object(collection,'execute_attempt') as execute:
            with self.assertRaisesRegex(ValueError,'runtime differs'):
                collection.collect(self.run,4)
            execute.assert_not_called()

    def test_calibration_version_difference_is_recorded_not_silently_merged(self):
        report=json.loads(self.evidence.read_text())
        report['runtime']={'cli_version':'OLDER-OFFLINE-FIXTURE'}
        planning.dump(self.evidence,report)
        self.config['tokenizer_calibration']['sha256']=planning.digest(self.evidence)
        manifest=self.prepare()
        self.assertFalse(manifest['calibration_runtime_matches_collection'])
        self.assertEqual(manifest['required_runtime'],self.runtime)

    def test_confirmation_refuses_character_matching(self):
        self.config['tokenizer']={'kind':'characters','characters_per_token':4}
        with self.assertRaisesRegex(ValueError,'calibrated tokenizer'):
            self.prepare()
        self.assertFalse(self.run.exists())

    def test_audit_boundary_is_inclusive_and_failed_execution_is_not_missing_usage(self):
        trials=[dict(world_id='w',model='m',effort='high',instruction='none',context=c,trial_id=c) for c in ['C','RG']]
        latest={c:{'eligible':True,'events':{'input_tokens':n}} for c,n in [('C',98),('RG',100)]}
        self.assertEqual(input_matching.audit(trials,latest,.02)[1]['status'],'passed')
        latest['C']['eligible']=False
        self.assertEqual(input_matching.audit(trials,latest,.02)[1]['status'],'pending')


if __name__=='__main__':
    unittest.main()
