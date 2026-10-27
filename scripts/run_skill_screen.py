"""Prepare and collect one explicitly configured, bounded development pilot."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from experiment.checks import check_world
from experiment.collect import Limits
from experiment.config import load_config
from experiment.runs import counted, operator_name, prepare, read_attempts, verify_collection_source
from experiment.screen_report import screen_report
from experiment.world import World


DESIGNS = {
    'skill_drafts_pilot.toml': (3, 5, 730000,
        {'none','ledger_v2','audit_v2','minimal_v2','budget_backward_v2','budget_forward_v2'}, 360),
    'minimal_checklist_v3_pilot.toml': (5, 10, 740000, {'none','minimal_v3'}, 400),
    'conflict_workflow_v1_pilot.toml': (5, 10, 750000, {'none','workflow_v1'}, 400),
    'conflict_workflow_v2_pilot.toml': (5, 10, 760000, {'none','workflow_v2'}, 400),
}


def validate_design(config, config_path):
    design = DESIGNS.get(Path(config_path).name)
    if design is None:
        raise ValueError('Unrecognized pilot configuration; refusing collection')
    logs, repeats, seed_start, instructions, planned = design
    if (config.logs != logs or config.repeats != repeats or config.seed_start != seed_start
            or set(config.instructions) != instructions or set(config.models) != {'gpt'}
            or set(config.versions) != {'C','R','RG','E'} or config.repeatability.logs
            or not config.generator.chronological or config.generator.records != 1600
            or not config.frozen_instruction_sha256):
        raise ValueError(f'Config differs from the authorized {planned}-call pilot')
    model = config.models['gpt']
    if (model.provider, model.model, model.effort) != ('codex', 'gpt-6-astra', 'low'):
        raise ValueError('Pilot requires GPT-6 Astra at low effort through the Codex client')
    return planned


def write_state(path, phase, **details):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(dict(phase=phase, pid=os.getpid(), **details), indent=2) + '\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--prepare-workers', type=int, default=3)
    parser.add_argument('--workers', type=int, default=10)
    parser.add_argument('--calls-per-minute', type=float, default=6)
    args = parser.parse_args()
    os.chdir(ROOT)
    state_path = args.run.parent / (args.run.name + '_job.json')
    base = dict(run=str(args.run), planned=None)
    child = None
    try:
        config = load_config(args.config)
        planned = validate_design(config, args.config)
        base['planned'] = planned
        if args.prepare_workers < 1:
            raise ValueError('prepare-workers must be positive')
        Limits(workers=args.workers, calls_per_minute=args.calls_per_minute)
        write_state(state_path, 'preparing', **base, workers=args.workers,
                    calls_per_minute=args.calls_per_minute)
        print(f'Generating {config.logs} fresh chronological logs; no model calls yet.', flush=True)
        run = prepare(config, args.config, args.run, operator_name(), workers=args.prepare_workers)
        for world_id in run.manifest['worlds']:
            world = World.from_json(json.loads((run.path/'worlds'/f'{world_id}.json').read_text()))
            problems = check_world(world, config.generator)
            if problems:
                raise RuntimeError(f'{world_id} failed validation: {problems}')
        if len(run.trials) != planned:
            raise RuntimeError('Unexpected call count; refusing collection')
        verify_collection_source(run)
        print(f'All logs validated; {len(config.instructions)-1} candidate(s) and the baseline frozen. '
              f'Starting {planned} calls.', flush=True)
        child = subprocess.Popen([sys.executable, '-u', '-m', 'experiment', 'collect', str(args.run),
            '--models', 'gpt', '--workers', str(args.workers), '--calls-per-minute', str(args.calls_per_minute)])
        write_state(state_path, 'collecting', **base, collector_pid=child.pid,
                    workers=args.workers, calls_per_minute=args.calls_per_minute)
        code = child.wait()
        print(screen_report(run), flush=True)
        completed = len(counted(read_attempts(run)))
        write_state(state_path, 'complete' if completed == planned else 'stopped', **base,
                    completed=completed, returncode=code)
        return code
    except KeyboardInterrupt:
        if child is not None and child.poll() is None:
            child.send_signal(signal.SIGINT)
            child.wait()
        write_state(state_path, 'stopped', **base, reason='Interrupted by user')
        return 130
    except Exception as error:
        if child is not None and child.poll() is None:
            child.send_signal(signal.SIGINT)
            child.wait()
        write_state(state_path, 'failed', **base, error=str(error))
        raise


if __name__ == '__main__':
    raise SystemExit(main())
