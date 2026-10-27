# Stopped development pilot

The user requested a stop near 100 completed responses to preserve subscription usage.
The collector exited on SIGINT (return code 130) with 107 eligible completions and
9 interrupted error attempts. The stop command was pending while the count passed
100. No further collection is authorized automatically. The completion heartbeat
was deleted. Preserve all attempts and frozen inputs.

Only one log completed all 80 matched responses; the other 27 eligible responses
remain available but do not enter the complete-log paired summary. These are
development data, not a completed five-log pilot or efficacy evidence. Keep all
five scheduled seeds 760000-760004 excluded from a future main evaluation.

The descriptive report is analysis/screen_report.txt. Do not resume or retry the
interrupted calls without a new explicit user request.

## Authorized two-log completion

On October 26 the user explicitly requested finishing s760001_n1600 and stopping
at two complete logs (160 eligible responses total). At resumption, 53 responses
were missing. scripts/finish_two_log_pilot.py selected that exact pending prefix
and launched the collector with --max-calls 53; it does not queue the third log.
No extra retries are launched automatically. Original frozen prompts and sources
passed hash verification. Earlier completed responses remain unchanged.

The original 107 eligible responses used codex-cli 0.163.0-alpha.11.2. The resumed
collector reports codex-cli 0.164.0-alpha.11.1. Model settings remain GPT-6 Astra/low,
but the installed CLI version changed between batches; disclose this collection
difference in the pilot report. CLI versions and isolation audits are saved per
attempt. Do not describe the two-log extension as a fully completed five-log study.

## Two-log extension (2026-10-27T05:05:18+00:00)

The user explicitly authorized finishing the second log only. This bounded invocation ended with 160/160 eligible responses. No third-log requests or automatic retries are authorized. The original five-log plan remains frozen and incomplete.
