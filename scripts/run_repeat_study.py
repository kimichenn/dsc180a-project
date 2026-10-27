"""Finish local preparation, verify the study, and collect the authorized GPT run."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from experiment.checks import check_world, check_chronological_range
from experiment.collect import Limits
from experiment.config import load_config
from experiment.runs import counted, load, prepare, read_attempts, verify_collection_source, operator_name
from experiment.world import World


def status(phase, **extra):
    path = ROOT/'runs/skill_repeat_10x_job.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(dict(phase=phase,pid=os.getpid(),**extra),indent=2)+'\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-run', type=Path, required=True)
    parser.add_argument('--prepare-pid', type=int, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=10)
    parser.add_argument('--calls-per-minute', type=float, default=6)
    args = parser.parse_args()
    Limits(workers=args.workers, calls_per_minute=args.calls_per_minute)
    os.chdir(ROOT)
    status('waiting_for_logs', prepare_pid=args.prepare_pid, workers=args.workers,
           calls_per_minute=args.calls_per_minute)
    print('Waiting for the already-running local generator; no model calls yet.', flush=True)
    # Bounded job wait, not a second generator or a retry of any model response.
    deadline = time.monotonic() + 6 * 3600
    while not (args.source_run / 'manifest.json').exists():
        try:
            os.kill(args.prepare_pid, 0)
        except ProcessLookupError:
            raise RuntimeError('Generator stopped before publishing its manifest; inspect preparation output.')
        if time.monotonic() > deadline:
            raise RuntimeError('Local preparation exceeded six hours; inspect it before continuing.')
        time.sleep(10)
    source = load(args.source_run)
    status('validating')
    config = load_config(args.config)
    for wid in source.manifest['worlds']:
        world = World.from_json(json.loads((source.path/'worlds'/f'{wid}.json').read_text()))
        problems = check_world(world, config.generator) + check_chronological_range(world.records, config.generator)
        if problems:
            raise RuntimeError(f'{wid}: {problems}')
    print('All 30 long logs passed answer, rendering, and chronological range validation.', flush=True)
    run = prepare(config, args.config, args.run, operator_name(), reuse_worlds=args.source_run)
    if len(run.trials) != 2400 or set(run.config.models) != {'gpt'}:
        raise RuntimeError('Unexpected model selection or trial count; refusing collection.')
    verify_collection_source(run)
    print(f'Frozen {len(run.trials)} GPT trials in {run.path}; starting collection.', flush=True)
    status('collecting', run=str(run.path), planned=2400, workers=args.workers,
           calls_per_minute=args.calls_per_minute)
    code = subprocess.call([sys.executable,'-u','-m','experiment','collect',str(args.run),
                            '--models','gpt','--workers',str(args.workers),
                            '--calls-per-minute',str(args.calls_per_minute)])
    subprocess.run([sys.executable,'-m','experiment','repeat-report',str(args.run)],check=True)
    completed = len(counted(read_attempts(run)))
    status('complete' if completed == 2400 else 'stopped', completed=completed, planned=2400, returncode=code)
    return code


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        status('failed', error=str(error))
        raise
