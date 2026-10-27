"""Finish only the second workflow-v2 log, with at most 53 additional requests."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from experiment.collect import pending
from experiment.runs import counted, load, now, read_attempts, verify_collection_source
from experiment.screen_report import screen_report

RUN = Path('runs/conflict_workflow_v2_pilot_v1')
STATE = Path('runs/conflict_workflow_v2_pilot_v1_job.json')
TARGET_WORLDS = ('s760000_n1600', 's760001_n1600')


def bounded_selection(run):
    verify_collection_source(run)
    done = counted(read_attempts(run))
    counts = Counter(t.world_id for t in run.trials if t.trial_id in done)
    if (set(run.config.models) != {'gpt'} or len(run.trials) != 400
            or counts[TARGET_WORLDS[0]] != 80
            or any(w not in TARGET_WORLDS for w in counts)):
        raise ValueError('Run differs from the authorized two-log completion')
    selected = [t for t in pending(run, ['gpt']) if t.world_id == TARGET_WORLDS[1]]
    if len(selected) > 53 or counts[TARGET_WORLDS[1]] + len(selected) != 80:
        raise ValueError('Refusing more than 53 requests or an incomplete second-log schedule')
    if pending(run, ['gpt'])[:len(selected)] != selected:
        raise ValueError('Pending prefix includes another log; refusing collection')
    return selected


def write_state(phase, **details):
    state = dict(phase=phase, pid=os.getpid(), run=str(RUN), planned=400,
                 target_completed=160, target_worlds=list(TARGET_WORLDS),
                 development_only=True, do_not_resume_automatically=True, **details)
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, indent=2)+'\n')
    temporary.replace(STATE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    os.chdir(ROOT)
    run = load(RUN)
    selected = bounded_selection(run)
    print(f'Bounded selection: {len(selected)} missing responses for {TARGET_WORLDS[1]}; '
          'stop at 160 eligible responses. No third-log requests.', flush=True)
    if args.check_only:
        return 0
    child = None
    try:
        if selected:
            child = subprocess.Popen([sys.executable, '-u', '-m', 'experiment', 'collect',
                str(RUN), '--models', 'gpt', '--max-calls', str(len(selected)),
                '--workers', '10', '--calls-per-minute', '6'])
            write_state('collecting_second_log', collector_pid=child.pid,
                        max_additional_requests=len(selected), workers=10, calls_per_minute=6,
                        reason='User explicitly requested finishing the second log only')
            code = child.wait()
        else:
            code = 0
        completed = len(counted(read_attempts(run)))
        print(screen_report(run), flush=True)
        finished = completed == 160
        write_state('two_logs_complete' if finished else 'stopped', completed=completed,
                    returncode=code, finished_at=now(),
                    reason='Two-log cap reached; no further calls authorized' if finished
                    else 'Bounded collection ended before the second log completed; no automatic retries')
        with (RUN/'DEVELOPMENT_ONLY.md').open('a') as f:
            f.write(f'\n## Two-log extension ({now()})\n\n'
                    f'The user explicitly authorized finishing the second log only. '
                    f'This bounded invocation ended with {completed}/160 eligible responses. '
                    'No third-log requests or automatic retries are authorized. '
                    'The original five-log plan remains frozen and incomplete.\n')
        return code if code else (0 if finished else 1)
    except BaseException as error:
        if child is not None and child.poll() is None:
            child.send_signal(signal.SIGINT)
            child.wait()
        write_state('stopped', completed=len(counted(read_attempts(run))),
                    reason=str(error) or 'Interrupted', finished_at=now())
        raise


if __name__ == '__main__':
    raise SystemExit(main())
