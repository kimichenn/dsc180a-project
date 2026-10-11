# Conflict-resolution EDA harness

Code for the study in [eda_proposal.md](eda_proposal.md). It covers scenarios, prompt building, model runs, labelling, analysis, and the stage decision rules.

## Setup

```bash
conda activate dsc180            # or: conda create -n dsc180 python=3.11 && pip install -r requirements.txt
cd eda/kimi
cp .env.example .env             # then paste OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY
```

Model IDs and reasoning settings live in [config/models.toml](config/models.toml). Freeze them before Stage 0. The diagnostic small models are in [config/small_models.toml](config/small_models.toml). Add `--models-config config/small_models.toml` to `run`, and results go to `results/small_models/`.

## Workflow

Run every command from `eda/kimi`.

| Step | Command |
| --- | --- |
| Automatic checks on scenarios and filler | `python -m conflict_eval validate` |
| Read the exact prompt (by-hand checklist) | `python -m conflict_eval preview vela-01 --variant consistent --question one_step` |
| Stage 0, see what would run | `python -m conflict_eval run stage0 --dry-run` |
| Stage 0 | `python -m conflict_eval run stage0` |
| Hand-label what string matching couldn't | `python -m conflict_eval label results/stage0_rung0` |
| Tables and the go / climb decision | `python -m conflict_eval analyze results/stage0_rung0` |
| Climb a rung if no model qualifies | `python -m conflict_eval run stage0 --rung 1` |
| Stage 1 at the frozen rung | `python -m conflict_eval run stage1 --rung R` |
| Stage 2 at the setting `analyze` picked | `python -m conflict_eval run stage2 --rung R --question two_step --distance far` |

Useful `run` flags: `--models gpt claude`, `--only vela-01`, `--workers 8`, `--out results/my_run`. Runs are resumable: rerun the same command and finished trials are skipped, failed ones retried. A run directory refuses to continue if the design or model settings change.

Each run directory gets:

- `responses.jsonl`: every raw response, with the full prompt, the expected answers, the exact model ID, and settings
- `labels.jsonl`: hand labels
- `manifest.json`: design, seed, model settings, scenario file hash, git commit, and session dates
- after `analyze`: `report.txt`, `scored.csv`, `scenario_results.csv` (one row per scenario cell, generations collapsed), `conflict_drop.csv` / `skill_recovery.csv` (per scenario), and `failures.md` (the read-through)

## Scenario format

[data/scenarios.json](data/scenarios.json) holds the 8 Stage 0 scenarios: 4 distractors and 4 updates, each split evenly between multi-document and multi-turn. The record follows the proposal, with these additions:

| Field | Purpose |
| --- | --- |
| `date` on each claim (ISO) | Orders claims chronologically and is shown to the model as "October 3" |
| `text` on each claim, with a `{value}` slot | The sentence the model sees. The harness fills in the value for each variant. |
| answers as a string or a list | A list gives accepted aliases, e.g. `["October 18", "10/18"]` |
| `ladder.paraphrase` (`conflict`, `consistent`) | Rung 2: replaces the later claim's text with a relative statement ("pushed back ten days") |
| `ladder.confidence_cue` | Rung 3: appended to the competing claim (default "This has been confirmed with the whole team.") |
| `ladder.extra_competing_claim` | Rung 4: a second non-governing source that agrees with the competing claim. Date it on the same side of the governing claim as the competing claim. |

A record without `ladder` supports rungs 0–1. `validate` reports which rungs each scenario supports. Use entity names that aren't common words or substrings of each other, because scoring matches them as whole words.

Filler passages are in [data/filler.json](data/filler.json). Rungs 0 and 1 use 2 and 4 passages. They are shared by every scenario and must not mention any scenario's sources, entities, or values (`validate` checks this).

## How prompts are built

```
[source rule]      rule placement = start
background         inference rule + supporting fact
lead filler
[source rule]      rule placement = near
claim segment      claims in date order; distance = far puts the mid filler between
                   the governing claim and the non-governing claim(s)
question
```

Multi-document prompts number these as `Document 1..n` in one user message. Multi-turn prompts send one user turn per block, with fixed `Understood.` assistant turns, and the question last. The system prompt holds only the common instruction plus the warning or skill. Scenario facts are always user-side.

## Where the code interprets the proposal

- **Consistent variant.** The later claim repeats the earlier claim's value, as the proposal says ("the second source agrees with the first"). For superseding updates this means the Consistent answer is the earlier value, which the Conflict version calls non-governing. The scorer accounts for this.
- **Lead filler.** A filler block always sits between the background and the claims. Without it, "rule at the start" and "rule next to the claims" would differ by a single block whenever distance is near.
- **Counterbalancing.** Multi-document prompts reverse the claim segment in half the cells. Matched Consistent/Conflict prompts and all three models always get the same order.
- **Stage 1 holds rule placement at "start"**, which matches the proposal's 432-response count. Add `--rule start near` to vary it (864 responses).
- **Scoring.** A response is auto-labeled when exactly one of the two candidate answers appears, when it names both but its first sentence (ignoring parentheses) names only the expected one, or when it clearly hedges and names neither. Everything else goes to `label`, so any response leading with the non-governing answer is checked by a person. `label` only asks which answer the response gave.
- **Conflict-mention flag** (whether the response points out that the sources disagree) is always automatic: wording like "unverified", "supersedes", "conflict", or a direct answer that names both values. It is never hand-labeled.
- **Collapsing generations.** Each scenario cell scores the share of generations labeled correct. The Stage 0 rule uses the majority. Stage 2 sums can be fractional (e.g. `7.5/12`).
- **Claude refusal fallbacks are off.** A fallback would answer with a different model. A refusal shows up as `finish_reason: refusal` and an empty response for hand-labelling.
