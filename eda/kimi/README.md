# Conflict-resolution EDA harness

Two harnesses share this folder:

- **`eventlog/` (v4, current):** the generated event-log design in [eda_proposal_v2.md](eda_proposal_v2.md). See the next section.
- **`conflict_eval/` (v3, Stage 0 done):** the single-conflict scenarios in [eda_proposal.md](eda_proposal.md), documented from [Setup](#setup) on. Its results are in `results/stage0_rung*`.

## v4: generated event logs

Each log covers N fictional Atlas projects. It contains a policy memo, an authority handover, a staff directory with one person who changes offices, a project roster, and changelog, email, and ticket records. Traps are non-governing launch dates placed across the question's threshold. The resolver ([eventlog/resolver.py](eventlog/resolver.py)) applies the memo's rules to compute every answer, and every log has a matched Consistent version.

| Step | Command |
| --- | --- |
| Generator validation (hand logs vs resolver, checks on generated logs) | `python -m eventlog validate` |
| Write one log pair to read end to end | `python -m eventlog generate --seed 1` |
| Stage A, see calls and estimated cost | `python -m eventlog run A --dry-run` |
| Stage A probe (18 calls) | `python -m eventlog run A` |
| Tables plus the decision rule, which prints the next command | `python -m eventlog analyze results/v4/A_step0` |
| Lower the general dials (Stage A rule 2) | `python -m eventlog run A --step 1` (through `--step 5`) |
| Stage A rule 3 options | `--set n_projects=200`, `--models-config config/v4_small_models.toml`, `--response-format final_only` |
| Stage B (126 calls) | `python -m eventlog run B --step K` |
| Stage C (108 calls, fresh seeds) | the command `analyze` prints after Stage B |

- **Configs.** Models, reasoning settings, and prices are in [config/v4_models.toml](config/v4_models.toml). Reasoning is set to `low`, the lowest level each flagship allows, standing in for "standard mode without extended reasoning".
- **Validation data.** The 12 hand-written logs are in [data/v4/hand_logs.json](data/v4/hand_logs.json).
- **Run directories.** Each run directory holds `logs/` (every generated log pair with its answer and per-project metadata), `responses.jsonl` (raw responses, including any first attempt that lacked an ANSWER line), and `manifest.json`.

**Where the code interprets the proposal:**
- **Dates.** Records are dated Sep 2 to Oct 31, and launch dates fall in Nov 3 to Dec 19, so issue dates and values never overlap.
- **Within-section order.** In grouped order, records inside each source section are shuffled, as in the proposal's example ticket export.
- **Trap placement.** Distractor notes and pre-authority records always come after the project's last counting record, so believing one changes the answer.
- **Pre-authority traps** come in two forms: a Release Board member writing before the handover, or the person who moves writing before their move.
- **Projects without traps** may also get an authoritative confirmation or an agreeing note, so a note's presence doesn't give a trap away.
- **Staff names** never share a first or a last name.
- **Out-of-program records** are as numerous as in-program ones. They are written by Helios staff about projects whose names extend Atlas names (e.g. Kavel and Kavelra).
- **Stage B ablation** runs Conflict logs only. Its conflict effect is measured against the Consistent error at the same N from the N sweep.

## Setup

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
