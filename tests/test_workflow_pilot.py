import hashlib
import tempfile
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from experiment.config import GeneratorSettings, load_config
from experiment.prompts import INSTRUCTIONS, SYSTEM
from experiment.runs import prepare, schedule, verify_collection_source
from scripts.run_skill_screen import validate_design


class WorkflowPilotTest(unittest.TestCase):
    config_path = Path('config/conflict_workflow_v1_pilot.toml')
    instruction = 'workflow_v1'
    folder = 'conflict-resolution-workflow-v1'

    def test_fresh_balanced_bounded_design(self):
        config = load_config(self.config_path)
        trials = schedule(config, [SimpleNamespace(world_id=str(s)) for s in config.seeds])
        self.assertEqual(validate_design(config, self.config_path), 400)
        self.assertEqual(len({t.trial_id for t in trials}), 400)
        self.assertEqual(Counter(t.instruction for t in trials), {'none': 200, self.instruction: 200})
        self.assertEqual(set(Counter((t.world_id,t.version,t.instruction) for t in trials).values()), {10})
        for old in ('skill_pilot.toml', 'skill_repeat_v2.toml', 'skill_repeat_10x.toml',
                    'skill_drafts_pilot.toml', 'minimal_checklist_v3_pilot.toml',
                    'conflict_workflow_v1_pilot.toml', 'conflict_workflow_v2_pilot.toml'):
            if old == self.config_path.name:
                continue
            self.assertFalse(set(config.seeds) & set(load_config(Path('config')/old).seeds))
        for changed in (replace(config, repeats=20), replace(config, logs=30),
                        replace(config, instructions=('none', 'minimal_v3'),
                            frozen_instruction_sha256={name: hashlib.sha256(INSTRUCTIONS[name].encode()).hexdigest()
                                                       for name in ('none', 'minimal_v3')})):
            with self.assertRaisesRegex(ValueError, 'authorized 400-call'):
                validate_design(changed, self.config_path)
        with self.assertRaisesRegex(ValueError, 'GPT-6 Astra at low'):
            validate_design(replace(config, models={'gpt':replace(config.models['gpt'], effort='high')}),
                            self.config_path)

    def test_exact_self_contained_treatment_and_unchanged_baseline_are_frozen(self):
        config = replace(load_config(self.config_path), logs=1, repeats=1,
                         generator=GeneratorSettings(records=40, chronological=True, max_attempts=500))
        body = (Path('experiment/skills')/self.folder/'SKILL.md').read_text().split('---',2)[2].strip()
        self.assertEqual(hashlib.sha256(body.encode()).hexdigest(), config.frozen_instruction_sha256[self.instruction])
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)/'run'
            with patch.dict(INSTRUCTIONS, {self.instruction:'changed after freeze'}):
                with self.assertRaisesRegex(ValueError, f'instruction {self.instruction} differs'):
                    prepare(config, self.config_path, folder, 'test')
            run = prepare(config, self.config_path, folder, 'test')
            self.assertEqual((folder/'system/none.txt').read_text(), SYSTEM)
            self.assertEqual((folder/'system'/f'{self.instruction}.txt').read_text(), SYSTEM+'\n\n'+body)
            self.assertTrue((folder/'source/experiment/skills'/self.folder/'SKILL.md').exists())
            self.assertEqual((folder/'PROTOCOL.md').read_text(), self.config_path.with_suffix('.md').read_text())
            verify_collection_source(run)


class WorkflowV2PilotTest(WorkflowPilotTest):
    config_path = Path('config/conflict_workflow_v2_pilot.toml')
    instruction = 'workflow_v2'
    folder = 'conflict-resolution-workflow-v2'


if __name__ == '__main__':
    unittest.main()
