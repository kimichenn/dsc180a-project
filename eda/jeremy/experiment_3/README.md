# Experiment 3: dense budget ledgers for flagship models

The goal is to find reproducible errors in **GPT-6 Astra, GPT-6.1 Sol, and GPT-6 Sol**, then determine whether misleading records cause additional errors. This is a development screen, not a confirmed finding.

Experiment 2 asks for one winning approval; many records can be ignored once that approval is established. Here the model must calculate a final budget from **every surviving adjustment**. There is one opening balance and no later reset that lets it discard earlier arithmetic. This changes the task substantially, so these results belong in a separate experiment.

The design is inspired by [Kimi's v5 budget study at commit 977328d](https://github.com/kimichenn/dsc180a-project/blob/977328dc52d606cb031ed7045e6e88dea1ab69f7/eda/kimi/reports/v5/findings.md). His saved 3,200-record Astra-low results were 3/5 clean and 3/5 conflict: evidence that this workload can produce wrong answers, but not a conflict-specific penalty on that small sample. Our new seeds, generator, instructions, terminal-answer format, and Codex wrapper differ. This is not an exact replication.

## Frozen development design

| Factor | Setting |
|---|---|
| Models | gpt-6-astra, gpt-6.1-sol, gpt-6-sol |
| Reasoning | Medium primary screen; low and high comparisons |
| Worlds | Five fresh generated worlds, seeds 300000–300004 |
| Records per world | 3,200 |
| Budget records | One opening balance plus 1,439 relative adjustments |
| Withdrawals | 480; can withdraw earlier withdrawals |
| Misleading messages | 960 unofficial team claims, all numerically false |
| Other messages | 320 neutral notes |
| Conditions | C: clean; RG: withdrawals plus misleading messages |
| Answer | Optional working, followed by exactly one `ANSWER: $<integer>K` line |
| Tools | Disallowed; tool events exclude the attempt from model-only accuracy |
| Planned calls | 5 worlds × 2 conditions × 3 models × 3 supported efforts = **90** |

The saved five worlds contain **1,179–1,205 surviving adjustments**, with maximum withdrawal-chain lengths of 5–9. Negative balances are explicitly allowed. Every condition has the same correct budget. These counts were checked before collection, without looking at model responses.

Clean controls replace withdrawals, cancelled adjustments, and misleading messages with harmless notes at the same IDs and positions, from the same authors. Surviving adjustments stay exactly the same. G-only and R-only variants are generated and validated for later ablations, but are not scheduled in this screen.

Two independent solvers check every key: backward resolution followed by summation, and forward replay that toggles effects when withdrawals arrive. Small withdrawal graphs are additionally checked by exhaustive truth assignments in the tests.

## Start collection

The frozen runs have already been prepared. Preparation and offline tests make no model requests.

```bash
cd /Users/jeremycheng/Documents/dsc180a-project/eda/jeremy/experiment_3
```

First check the new answer format on five tiny Astra-medium examples:

```bash
python3 run.py collect --run results/smoke_v1 --models gpt-6-astra --efforts medium --max-new-trials 5
```

All five should be correct and eligible. If there is an interface failure, inspect it before starting the long ledger task. A wrong numeric answer on a tiny example also needs review; do not silently rerun it.

Then start **Astra at medium reasoning on the long ledgers**:

```bash
python3 run.py collect --run results/flagship_dense_v1 --models gpt-6-astra --efforts medium --max-new-trials 10
```

This completes all five C/RG pairs for Astra-medium. Finish the other two models' medium trials with:

```bash
python3 run.py collect --run results/flagship_dense_v1 --efforts medium --max-new-trials 30
```

Completed Astra trials are skipped, so that command adds **20** calls if the first ten finished. Repeating either command resumes unfinished cells; it never replaces a completed wrong answer.

After all 30 medium trials, collect the predeclared effort comparisons:

```bash
python3 run.py collect --run results/flagship_dense_v1 --efforts low high --max-new-trials 60
```

Use a smaller `--max-new-trials` for bounded batches. The schedule is shuffled and fixed. Do not end a model/effort comparison as soon as a wrong answer appears. The tiny smoke cases are excluded from development results.

To refresh summaries without making model calls:

```bash
python3 run.py analyze --run results/flagship_dense_v1
```

## What a wrong answer would establish

- **Clean and conflict both fail:** an error on dense accounting; it does not establish an effect of misleading information.
- **Clean succeeds while conflict fails:** a candidate conflict effect. A useful screening rule is C ≥ 4/5 and RG ≤ 3/5 at the same reasoning effort. Five worlds are too few for a strong population claim.
- **Low fails but medium/high succeeds:** an effort-sensitive failure. Report the setting and token use; do not describe the model as failing at every reasoning level.
- **High still fails:** a stronger case study, followed by independent validation on fresh worlds. High is not the maximum advertised effort; xhigh/max would be a later explicitly frozen comparison.
- **Everything succeeds:** this workload did not break these models on this sample. Complete the planned comparisons, then increase the number of answer-relevant adjustments in a new run rather than changing saved prompts.

For a promising conflict-specific setting, freeze one model/effort and 30 fresh paired worlds starting at seed 400000. Complete all 60 eligible trials. The planned operational threshold is C ≥ 27/30, RG ≤ 18/30, a paired gap ≥ 30 percentage points with its 95% interval excluding zero, and at least 29/30 valid-format outputs in each condition. Do not pool those confirmation worlds with development. A single verified wrong budget is a failure example; it does not by itself establish this threshold or explain the model's internal reasoning.

If the fresh-world gap holds, collect G-only and R-only ablations before attributing the effect to gossip or withdrawals individually. Added conflict-resolution instructions and neutral instruction controls are later experiments.

## Responses, tokens, and limitations

Each attempt saves the exact prompt and policy, command, CLI version, raw events, response, receipt, and elapsed time. Run manifests freeze questions, answer keys, settings, catalog, and source hashes. The collection harness was copied and adapted from Experiment 2; see [provenance](HARNESS_PROVENANCE.md). Experiment 2's collector and existing runs are unchanged.

- `scored.csv`: expected and returned budgets, signed/absolute error, format, outcome, and audit eligibility.
- `summary.csv`: accuracy, wrong budgets, abstentions, format failures, numeric-only absolute error, coverage, and tokens by model/effort/condition.
- `token_usage.csv`: reported **input and output tokens for every attempt**, including failed attempts; cached input and reasoning usage remain separate.
- `paired_effects.csv`: C/RG differences on the same worlds.
- `reasoning_effects.csv`: effort differences on the same worlds.
- `responses.jsonl` and `attempts/`: complete saved response and event evidence.

Output and reasoning token totals are not added together; reasoning may already be included in output. Missing usage stays missing. Summaries distinguish all-attempt totals from attempts included in accuracy. Infrastructure failures, tool use, and event mismatches are excluded from accuracy and retained in coverage. Wrong answers, abstentions, and malformed completed answers are never automatically retried.

The initial prompts use roughly 59,000–60,000 **estimated** task tokens per call. These are character-based estimates, not reported model usage, and omit the CLI's additional context. Actual input/output usage must be checked after collection. Neutral padding brings estimated condition lengths within 2%; exact tokenizer matching is unverified. The CLI's output-token cap is not enforced; a 15-minute wall-clock timeout is enforced and recorded separately from answer errors.

The cached model catalog does not advertise `none` reasoning for these models. Those combinations are recorded as unsupported, not silently replaced with low. Model aliases and a CLI version do not independently verify a served checkpoint. This is a tools-disabled Codex evaluation, not a statement about tool-enabled agents or the paid API.

## Reproduce preparation and offline validation

Only use new run names; the existing directories are already frozen.

```bash
python3 -m unittest discover -s tests -v
python3 run.py prepare --stage smoke --config config_smoke.json --run results/smoke_new
python3 run.py prepare --stage development --run results/flagship_dense_new
```

Confirmation preparation requires a separate reviewed configuration with one model/effort, one record count, and fresh seeds, plus `--development-reviewed`. Character-based matching also requires explicitly recording `--allow-estimated-tokens`.
