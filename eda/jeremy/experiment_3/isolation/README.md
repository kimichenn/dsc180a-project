# Misleading-message isolation at Astra high

This separate follow-up asks whether misleading messages reduce exact budget accuracy when the withdrawal workload is held fixed. It uses 30 fresh paired worlds (seeds 500000–500029), 3,200 records each, Astra high, no tools, and no added skill: 60 responses.

| Condition | Contents |
|---|---|
| R | All budget adjustments and withdrawals; misleading messages replaced by harmless administrative notes |
| RG | Identical adjustments and withdrawals; the misleading messages remain |

The answer, official records, withdrawal chains, record positions, authors, and unrelated messages are identical within each pair. Preparation verifies this directly and checks every answer with two independent solvers. Local token counts are matched to within one token by neutral padding before the final question. This matches total input length, not every record's token position.

## Collect the prepared run

```bash
cd /Users/jeremycheng/Documents/dsc180a-project/eda/jeremy/experiment_3
python3 isolation/run.py collect --run results/isolation_astra_high_v1 --models gpt-6-astra --efforts high --max-new-trials 60 --retry-errors
```

The prepared inputs need only `python3` and the ChatGPT-signed-in Codex CLI. The tokenizer package is needed only for preparation and offline tokenizer tests. Collection resumes unfinished trials and retains all attempts; wrong answers, abstentions, and completed malformed answers are never retried. Do not run two collectors against the same directory. Keep the terminal open and the Mac awake. The preceding 60-trial C/RG run took about 4 hours 41 minutes; this comparison's duration may differ.

World order and order within each pair are randomized; paired calls are adjacent. The collector stops for a runtime change, an execution/interface failure, missing reported input usage, or a reported input-length gap above 2%. Preserve the evidence and inspect the cause before continuing; do not edit the frozen manifest or discard a failed pair.

## Frozen interpretation

The primary contrast is **R minus RG exact-answer accuracy**. Wrong budgets and abstentions are reported separately; both count as incorrect for this primary metric.

Complete all 30 pairs. Evidence of an added misleading-message penalty requires a positive accuracy gap, a 95% paired bootstrap interval entirely above zero, and a two-sided exact paired discordance test (McNemar/binomial) with p < 0.05. Require 60 eligible responses, at least 29/30 valid-format responses in each condition, and all 30 input-length pairs within 2%. The bootstrap uses 2,000 world resamples and seed 180; the exact test conditions on pairs where only one answer is correct.

This is one new, prespecified comparison. There is no fixed 30-point minimum for this different question. The preceding C/RG run's original criteria remain unchanged: its 30/30 versus 22/30 result missed the full rule. Do not pool its worlds with this run or reinterpret it as passing. A nonsignificant result here does not establish equivalence or prove that misleading messages have no effect; 30 pairs can miss small effects.

The result concerns replacing neutral messages with this generator's false unofficial claims at a fixed withdrawal workload. It does not identify the model's internal reasoning, establish adoption of a particular false claim, or test a skill benefit.

```bash
python3 isolation/run.py analyze --run results/isolation_astra_high_v1
```

Inspect `progress.json`, `summary.csv`, `scored.csv`, `paired_effects.csv`, `input_length_audit.csv`, and `token_usage.csv`. The paired table includes both discordant counts and `exact_p_two_sided`; the length audit uses `R_input_tokens` and `RG_input_tokens`.

## Provenance and limitations

The collector was copied from `../confirmation` so the completed C/RG run and its frozen source hashes remain valid. The ledger generator, terminal-answer scorer, task instructions, token matcher, and calibration evidence were copied unchanged. The preparation checks and live audit now require R/RG pairs; paired analysis adds exact discordance statistics. See `source_provenance.json` for original hashes.

The existing tokenizer calibration used saved development C/RG responses. It is empirical calibration rather than proof of Astra's tokenizer or hidden framing, and its transfer to R/RG still requires the live usage audit. Exact model tokenization remains unverified. The model alias is not a pinned served checkpoint. The 900-second per-attempt timeout is enforced; the requested output-token cap is not enforced. Reasoning-output tokens are retained separately, not added to output totals again.

## Reproduce preparation offline

Only use a new output directory when preparing another run. Install `requirements-prepare.txt` in a separate environment if needed, then:

```bash
python3 -m unittest discover -s isolation/tests -v
python3 isolation/run.py prepare --stage confirmation --config isolation/config.json --run results/isolation_astra_high_new --development-reviewed --allow-estimated-tokens
```

Before any new collection, verify the seeds are disjoint from all previous runs, freeze the intended runtime, inspect the manipulation/token checks, and preserve the decision criteria. Preparation and the tests send no model requests.
