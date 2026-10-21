# Astra-high confirmation with token-matched inputs

This is a separate version of the Experiment 3 harness. The original source and completed development runs remain intact. `ledger.py`, `run.py`, and the common task instructions were copied unchanged; the token matcher, planning, and collection audit were revised here.

The prepared run is `../results/confirmation_astra_high_v1` relative to this folder: **30 fresh worlds, seeds 400000–400029, with one clean and one combined-conflict prompt per world, for 60 Astra-high responses**. Each world still has 3,200 records. All calls use the same common rules, no added skill, and no tools. Two independent solvers validate every answer key.

## Run collection

From any terminal:

```bash
cd /Users/jeremycheng/Documents/dsc180a-project/eda/jeremy/experiment_3
python3 confirmation/run.py collect --run results/confirmation_astra_high_v1 --models gpt-6-astra --efforts high --max-new-trials 60 --retry-errors
```

The inputs are already generated; collection needs only the same `python3` and ChatGPT-signed-in Codex CLI used previously. It does not need a paid API key or the preparation-only tokenizer package. The command resumes unfinished work. `--retry-errors` permits up to three attempts for infrastructure failures; it never retries a completed wrong answer or abstention. A usage limit, timeout, or interface failure stops the batch with the evidence saved.

The CLI version and settings are frozen for this run. If Codex updates again, collection stops rather than mixing versions. Do not edit the manifest to bypass a version or input-matching check.

## What changed

The old character-divided-by-four estimate matched characters but left a roughly 20% difference in actual input tokens. The new matcher counts text with `tiktoken` 0.14.0, `o200k_base`, searches a fixed token target, and adds neutral padding only after the ledger and before the final question. It preserves every record and its position, every valid adjustment, and the answer. Local text counts are matched to within one token; the configured tolerance is 0.1%.

The tokenizer was calibrated against **30 saved Astra responses, forming 15 C/RG comparisons across five development worlds and three effort settings**. Its prediction of each paired input-count difference was within four tokens of the reported difference. `cl100k_base` was also checked and gave the same paired-error bound. The evidence and hashes are saved in `tokenizer_calibration.json` and copied into the frozen run. Calibration made no model calls and did not use confirmation answers.

This is empirical calibration, not verification of Astra's exact server tokenizer or hidden request framing. [OpenAI's token-counting documentation](https://developers.openai.com/api/docs/guides/token-counting) distinguishes local text counts from full processed request counts. Accordingly, `prompt_tokens_exact` stays false; preparation records the calibrated-count deviation explicitly rather than claiming exact API accounting.

Development used `codex-cli 0.162.0-alpha.17.2`; the installed confirmation runtime is `codex-cli 0.163.0-alpha.10.2`. Both versions are recorded separately. The updated runtime has not yet produced confirmation responses, so actual matching remains to be verified during collection.

## Live length checks

World order and the order within each pair are randomized with seed 180, but each world's two calls are adjacent. This lets the collector verify a pair before proceeding to the next world.

After each attempt, `input_length_audit.csv` records reported C and RG input tokens. The gap is `abs(C - RG) / max(C, RG)`. Collection stops if a completed response lacks valid reported input usage or if a completed pair exceeds **2%**. Resuming a run with a failed length audit is blocked. All responses remain saved and their answer scores remain unchanged; no mismatched pair is silently removed from the data. Investigate the cause and create a new frozen run if a design change is required.

Missing/failed execution remains an infrastructure problem, not a zero token count. All 30 pairs must pass the input audit before making confirmation claims. Raw input/output usage, cached input, reasoning output, elapsed time, and failed attempts remain separate. Reasoning tokens are not added to output totals again. The inherited 900-second timeout is enforced; the requested 32,000-output-token allowance remains unenforced by the CLI.

## Analysis and interpretation

```bash
python3 confirmation/run.py analyze --run results/confirmation_astra_high_v1
```

Read `progress.json`, `input_length_audit.csv`, `summary.csv`, `paired_effects.csv`, `scored.csv`, and `token_usage.csv`. The primary comparison is C minus RG exact-answer accuracy at Astra high, with wrong budgets and abstentions reported separately. The existing confirmation thresholds remain C at least 27/30, RG at most 18/30, a paired gap of at least 30 percentage points with its 95% paired bootstrap interval excluding zero, and at least 29/30 valid-format outputs in each condition. Complete all 60 eligible responses; do not stop after a numerical error.

This confirms the **combined withdrawal and misleading-message task**, if the pattern repeats. It does not isolate misleading information alone or measure a skill benefit. Those require later withdrawal-only/misleading-message-only controls and skill/neutral/no-skill comparisons. Keep confirmation results separate from the five development worlds.

## Reproduce preparation

Only preparation and the tokenizer tests require `requirements-prepare.txt`. A virtual environment can be created inside this folder as `.venv` (already ignored by the repository):

```bash
python3 -m venv confirmation/.venv
confirmation/.venv/bin/python -m pip install -r confirmation/requirements-prepare.txt
confirmation/.venv/bin/python -m unittest discover -s confirmation/tests -v
confirmation/.venv/bin/python confirmation/run.py prepare --stage confirmation --config confirmation/config.json --run results/confirmation_astra_high_new --development-reviewed --allow-estimated-tokens
```

Use a new run name; never overwrite the existing run. The explicit estimate flag records uncertainty about server framing; confirmation preparation additionally requires the calibrated tokenizer, intact evidence, and the live input-length guard. It cannot fall back to character matching. `calibrate_tokens.py` can reproduce the saved calibration from the old run with a new output filename.
