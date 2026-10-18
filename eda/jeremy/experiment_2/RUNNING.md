# Collect Experiment 2 with Codex

The generator, two independent answer solvers, strict answer checker, and batch
collector use Python's standard library. No API key or Python package install is
needed for the default workflow. Collection requires Codex signed in with ChatGPT.

See [VALIDATION.md](VALIDATION.md) for the 27 passing offline tests and six saved
live smoke checks. Long development and confirmation collection has not started.

## Start with short questions

```bash
cd /Users/jeremycheng/Documents/dsc180a-project/eda/jeremy/experiment_2
python3 run.py check
python3 run.py models
python3 run.py prepare --stage smoke --run results/smoke_v2
python3 run.py collect --run results/smoke_v2 --max-new-trials 10
```

`prepare` creates questions and freezes settings; it sends no model requests.
A `results/smoke_v2` plan is already prepared in this checkout; skip its preparation command and use `collect` to resume. For another fresh run, choose a new directory name. The earlier `smoke_v1` contains preserved integration diagnostics from before the startup-warning fix and cannot be resumed with the revised collector.
Each collection command makes at most the requested number of **new attempts**.
Repeat the same collection command to continue. Correct and incorrect completed
answers are both final; neither is retried to improve accuracy.

The full default smoke matrix has five hand-worked questions for each supported
model/effort pair. Start here to verify access and the saved output before long
questions. To restrict a batch without changing the frozen plan:

```bash
python3 run.py collect --run results/smoke_v2 --models gpt-6-astra --efforts medium --max-new-trials 5
python3 run.py analyze --run results/smoke_v2
```

## Models and reasoning levels

Edit [config.json](config.json) **before preparing a new run**. Defaults request:

| Models | Requested efforts |
|---|---|
| `gpt-6-astra`, `gpt-6.1-sol`, `gpt-6-sol`, `gpt-6-luna` | `none`, `low`, `medium`, `high` |

The local catalog observed during implementation advertises low/medium/high for
these four models, but not `none`. Unsupported pairs appear in
`unsupported_combinations.csv` and are not scheduled. **Low is not off.** A future
catalog advertising `none` permits that combination in a newly prepared run;
its attempts additionally require a reported reasoning-token count of zero.
Missing counts leave the reasoning-off claim unverified and exclude the attempt.

Use `python3 run.py models` to inspect current cached capabilities. Availability
is verified by actual attempts, not guaranteed by the catalog. `--catalog PATH`
can read a saved Codex model-cache file. Never supply an authentication file.
You can add advertised `xhigh` or `max` settings to a new plan. `ultra` is excluded
because it may delegate work and would change this single-model experiment.

The API's [reasoning capabilities](https://developers.openai.com/api/docs/guides/reasoning)
are a separate interface: support there does not imply support in your installed
Codex CLI. This collector does not switch to API billing or substitute models.

## Move to long development questions

After checking smoke responses and logs:

```bash
python3 run.py prepare --stage development --run results/development_v1
python3 run.py collect --run results/development_v1 --efforts medium --max-new-trials 10
python3 run.py analyze --run results/development_v1
```

There are five worlds at depths 2/4/8, each with matched C and RG conditions.
With four models and three supported efforts, that is **360 planned calls**;
the commands above run only ten. Start at medium, then run bounded batches for
low/high or omit filters to follow the full randomized schedule. Keep paired
conditions reasonably close in time; model aliases can change behind the service.

The same world, prompt, and answer key are used across model/effort settings.
Every trial is a fresh session. C is the clean ledger; RG adds invalidated evidence
and misleading summaries. Confirmation also includes G (summaries only), R
(revocations only), and none/neutral/skill instruction treatments.

Review the development screening rule in [README.md](README.md) before choosing
one confirmation depth. Use new seeds for confirmation and freeze the choice in a
separate config file. The default confirmation depth is a placeholder. Example:

```bash
python3 run.py prepare --stage confirmation --run results/confirmation_v1 \
  --config confirmation_config.json --development-reviewed --allow-estimated-tokens
```

Create and review `confirmation_config.json` first. `--allow-estimated-tokens`
explicitly records a methodological deviation: default prompt matching uses
characters divided by four, not a verified model tokenizer. Without that flag,
confirmation requires a named `tiktoken` encoding and `verified_for_models` entries
whose mapping you have independently verified; setting a flag alone is not that
verification. The full default confirmation design is **4,320 calls**. Preparation
does not start them; budget from development usage before collecting.

## Saved outputs

| File | Purpose |
|---|---|
| `manifest.json` | Frozen configuration, capability snapshot, code/input hashes, limitations |
| `worlds.jsonl`, `trials.jsonl` | Answer keys and randomized trial schedule; keys are never sent to the model |
| `prompts/`, `instructions/` | Exact saved experimental inputs |
| `validation.json`, `baselines.csv` | Solver agreement, prompt estimates, latest-approval and repeated-route shortcuts |
| `attempts/<trial>/<number>/` | Exact prompt/system text, command, raw events, final answer, diagnostics, receipt |
| `responses.jsonl` | Rebuildable consolidated view of every saved attempt |
| `token_usage.csv` | Input/output/cached/reasoning counts for every attempt, including failures and retries |
| `scored.csv`, `summary.csv` | Full planned coverage, errors, accuracy, token totals/means/medians by condition |
| `paired_effects.csv` | Within-world context comparisons |
| `reasoning_effects.csv` | Within-model, within-world effort comparisons |
| `instruction_effects.csv` | Within-world skill/neutral/no-instruction comparisons |
| `progress.json` | Collected, eligible, missing, and error counts |

Per-attempt files are retained; analysis tables are rebuilt atomically. Usage is
preserved as reported, with missing fields left null/blank. Cached input and
reasoning output are not added to input/output again. Summaries distinguish all
attempts from attempts included in accuracy and report how many attempts have
each usage field. Known totals may therefore be incomplete. No API dollar charge
is inferred from subscription usage.

Scoring accepts exactly the final JSON object with `route` and `approval_id`.
Explanations, duplicate keys, code fences, or a correct answer mentioned inside
prose do not pass. Abstention, wrong route, wrong approval, route/ID mismatch,
malformed output, and infrastructure failures have separate labels. Eligible
malformed answers count as incorrect; execution/interface failures are excluded
from accuracy and remain visible in coverage.

## Failures and resuming

A quota, timeout, or interface problem stops the batch after saving the attempt.
Read its `stderr.log`, `events.jsonl`, and receipt before continuing. Transient
execution failures can be retried explicitly, up to three total attempts per cell:

```bash
python3 run.py collect --run results/smoke_v2 --max-new-trials 5 --retry-errors
```

Configuration errors, tool activity, unsupported settings, and completed wrong
answers are not automatically retried. Fix configuration/code in a **new run**;
changing frozen inputs, collection code, or the CLI version blocks resumption.
Ctrl-C saves an interrupted attempt. An abrupt process kill can leave a
`.collecting` lock: inspect its PID and confirm that no collector or child is
running before removing that lock. A partial attempt is retained as interrupted,
not inferred to be a completed answer.

The harness replaces Codex's normal model instructions with the study rules,
disables documented tool/delegation features, ignores user config, and uses an
empty temporary working directory. Actual event logs are still audited: observed
tool calls, errors, additional turns, or unexpected events exclude a trial.
Managed/service instructions may remain; label results as **Codex-mediated**.
Requested model IDs are not pinned served checkpoints. The proposed 32,000-output-
token cap is not enforced; the 900-second timeout is only a wall-clock limit.
See the official [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
and [non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).

## Offline verification

```bash
python3 -m unittest discover -s tests -v
```

Tests cover independent solver agreement, matched controls, strict scoring,
unsupported reasoning settings, pairing, token accounting, quotas, interruptions,
resume behavior, and event exclusions. Fake CLI responses exist only in temporary
test directories and are never stored as experiment results.
