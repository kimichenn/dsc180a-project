# Conflict-resolution EDA

Do language models follow a stated rule when the records they read disagree? Each experiment here generates prompts whose correct answer is computed independently of the model, runs models on them, and scores the answers. Every prompt has a matched version without the conflict, so a drop in accuracy can be traced to the conflict rather than to length or difficulty.

| Experiment | Package | Question asked of the model | Status | Docs | Write-up |
| --- | --- | --- | --- | --- | --- |
| v5 budget chains | `chain/` | One project's budget after N official updates, unofficial notes, and withdrawals | Break phase run on P0 (N 20-3200) | [chain/README.md](chain/README.md) | [reports/v5/findings.md](reports/v5/findings.md) |
| v4 event logs | `eventlog/` | Which of N projects launch before a date, across a multi-source log | Stage A done | [eventlog/README.md](eventlog/README.md) | [reports/v4/eda_report.md](reports/v4/eda_report.md) |
| v3 single conflicts | `conflict_eval/` | One fact stated two ways in a short scenario | Stage 0 done | [conflict_eval/README.md](conflict_eval/README.md) | |

## Setup

- Python 3.11 (the `dsc180` conda environment): `pip install -r requirements.txt`.
- API keys go in `.env` (copy `.env.example`); `.env` is gitignored. v3, v4, and any Gemini model use them. v5 runs GPT and Claude through the logged-in Codex and Claude Code CLIs instead (see [chain/README.md](chain/README.md)).
- Run every command from `eda/kimi`: `python -m <package> --help`.

## Layout

```
harness/            shared by every experiment, with no experiment logic
  models.py           model configs, API clients, .env loading
  subscriptions.py    the same interface over the Claude Code and Codex CLIs
  calls.py            retries, and the error that stops a run
  runs.py             responses.jsonl + manifest.json in a run directory, token counting
  prompts.py answers.py names.py   the Prompt type, the ANSWER-line pattern, made-up codenames
chain/ eventlog/ conflict_eval/      one package per experiment (python -m <package>)
config/<version>_models.toml         models, reasoning levels, prices, context windows
data/<version>/                      hand-checked cases and fixed inputs
results/<version>/<run>/             raw responses, manifest, and analysis outputs per run
reports/<version>/                   write-ups and the scripts that draw their figures
```

Runs are resumable: rerun the same command and finished calls are skipped, failed ones retried. A run directory refuses to continue if its plan or model settings change.

## Adding an experiment

1. Create a package with a `cli.py` and `__main__.py`. Import shared pieces from `harness` only, never from another experiment, so older experiments can change without breaking newer ones.
2. Give it `config/vN_models.toml`, `data/vN/`, `results/vN/`, and `reports/vN/`.
3. Document it in a README inside the package and add a row to the table above.
