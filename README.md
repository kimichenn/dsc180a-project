# Resolving Conflicting Records in Long-Context Language Models

This **DSC 180A capstone** tests whether language models can work out a project's current budget from a long log of updates, false claims, and canceled changes. We generate synthetic logs with known answers to compare how models handle each kind of conflict.

We ask three questions:

1. Do models struggle with canceled updates (withdrawals) or with the arithmetic?
2. Can a **conflict-resolution skill** (a written guide added to the prompt) reduce withdrawal errors?
3. Does a model give the same answer when it sees the exact same prompt several times?

## The task

The model reads a chronological log and answers: **What is the budget now?** Only the Finance Office can change the budget. Other sources' claims are _gossip_ and do not count. Finance can withdraw an earlier update, and withdrawing that withdrawal restores the original update.

```text
#001  Finance Office: Kavel budget set to $800K.
#002  Engineering email: Kavel budget is going up to $950K.
#003  Finance Office: Kavel budget increased by $40K.
#004  Finance Office: Kavel budget decreased by $15K.
#005  Finance Office: Withdraw update #003.
#006  Finance Office: Kavel budget increased by $25K.
```

The answer is **\$810K**: \$800K − \$15K + \$25K. The Engineering claim does not count, and #005 cancels the \$40K increase in #003.

## Experimental design

The main study compares four versions of each log:

| Version                    | What the log contains                                             |
| -------------------------- | ----------------------------------------------------------------- |
| C: clean                   | No gossip or withdrawals                                          |
| R: withdrawals             | Withdrawals, including withdrawals of withdrawals                 |
| RG: withdrawals and gossip | Both                                                              |
| E: explicit reversals      | Withdrawals replaced by equivalent budget increases or decreases  |

All versions have **the same correct answer and number of records**, with similar text lengths. Comparing R with E helps separate withdrawal logic from arithmetic difficulty.

The proposed main study compares **Claude Opus 5.5 and GPT-6 Astra** at **1,600 records per log**. The development runs below collected **GPT-6 Astra at low reasoning effort only**; no Claude responses were collected in these runs.

- **Pilot:** [config/trial.toml](config/trial.toml) checks difficulty and timing with five logs across all four versions, without the skill (**20 calls per model**).
- **Latest adaptive-workflow pilot, stopped after two complete logs:** [config/conflict_workflow_v2_pilot.toml](config/conflict_workflow_v2_pilot.toml) originally planned five logs and 400 responses. To preserve subscription usage, collection stopped at 107 responses, then a bounded extension completed the second log for **160 eligible responses total**. No third-log attempts were made. The current candidate is [conflict-resolution-workflow-v2](experiment/skills/conflict-resolution-workflow-v2/SKILL.md), experiment condition `workflow_v2`. It routes uncomplicated evidence directly and makes segmentation optional. See the [original protocol](config/conflict_workflow_v2_pilot.md), [collection history](runs/conflict_workflow_v2_pilot_v1/DEVELOPMENT_ONLY.md), and [results report](runs/conflict_workflow_v2_pilot_v1/analysis/screen_report.txt). Gstack itself is not loaded or executed in the experiment.
- **Completed workflow-v1 pilot:** All 400 calls completed: overall accuracy was 72.5% with skill versus 74% without; R/RG improved by 8 percentage points, while C/E decreased by 11. See the [results report](runs/conflict_workflow_v1_pilot_v1/analysis/screen_report.txt). The [clean-case failure review](runs/conflict_workflow_v1_pilot_v1/analysis/workflow_v1_clean_failure_review.md) motivates v2.
- **Superseded minimal-checklist pilot:** [config/minimal_checklist_v3_pilot.toml](config/minimal_checklist_v3_pilot.toml) was stopped during local preparation before any model calls. The untested draft remains available, but is not an active run.
- **Completed five-draft screen:** [config/skill_drafts_pilot.toml](config/skill_drafts_pilot.toml) collected all 360 calls. No draft beat the baseline's overall accuracy; minimal v2 tied it at 49/60 and did not meet the advancement heuristic. See its [results report](runs/skill_drafts_pilot_v1/analysis/screen_report.txt) and [minimal-v2 failure review](runs/skill_drafts_pilot_v1/analysis/minimal_v2_failure_review.md).
- **Stopped GPT repeat study:** [config/skill_repeat_10x.toml](config/skill_repeat_10x.toml) planned 2,400 calls. The user stopped it at **267 eligible responses** to revise the skill and run a smaller screen. Its inputs and results are preserved as development data; do not resume it or pool it with a future evaluation. See [the stop record](runs/skill_repeat_10x_v1/DEVELOPMENT_ONLY.md) and [incomplete report](runs/skill_repeat_10x_v1/analysis/repeat_report.txt).
- `config/main.toml` retains the older draft design; it is not the current repeat-study configuration.

### Latest two-log results

The two completed logs are seeds **760000 and 760001**. Each has four versions,
two instruction conditions, and ten repeats: **80 responses per log**, or **80 per
instruction across both logs**. There are 160 eligible responses and nine preserved
error attempts from the earlier interruption. The other three prepared logs have
no attempts. Collection is stopped; the original frozen five-log configuration
and manifest still describe 400 planned responses.

| Version | No skill | Workflow v2 | Paired change (percentage points) |
| --- | ---: | ---: | ---: |
| C | 75% | 90% | +15 |
| R | 35% | 55% | +20 |
| RG | 55% | 85% | +30 |
| E | 80% | 75% | -5 |
| **Overall** | **61.25% (49/80)** | **76.25% (61/80)** | **+15** |

The report averages repeats within each log and weights the two logs equally.
R/RG accuracy increased by 25 percentage points on average, with per-log gains
of +35 and +15 points. C/E increased by 5 points on average, but E alone decreased
by 5 points. Exact-answer pair agreement across repeats was 41.7% without skill
and 59.4% with skill. Mean output tokens were approximately 3,515 and 3,659.

These are **exploratory development results from two independent budget logs**.
There are no significance tests or claims of cross-domain effectiveness. The
original advancement criteria cannot be declared satisfied: only two of five
logs were completed and E degraded. This pilot does not directly compare v2 with
older drafts, which used different logs. Keep all earlier runs separate.

The original 107 responses used Codex CLI `0.163.0-alpha.11.2`; the 53-response
extension used `0.164.0-alpha.11.1`. The model settings and frozen experiment
sources were unchanged, but the CLI version changed between collection batches.
Disclose this in any pilot report. All five prepared seeds, 760000-760004, remain
development data and are excluded from a future main evaluation.

Inspect the saved results without making model calls:

```bash
python3 -m experiment status runs/conflict_workflow_v2_pilot_v1
python3 -m experiment screen-report runs/conflict_workflow_v2_pilot_v1
```

Completed eligible responses are never rerun. The collector verifies frozen inputs
and source hashes before resuming. Logs and execution source are captured in the run;
later edits do not silently change its protocol. The local generator can need many
rejection attempts to keep the chronological total within the specified range.

Drafts live in [experiment/skills/](experiment/skills/). The harness inserts only the
selected Markdown body; it does not rely on automatic skill selection. The bounded
extension in [scripts/finish_two_log_pilot.py](scripts/finish_two_log_pilot.py) finished
the second log only. No further collection or automatic retry is authorized for
the saved pilot. Preparing or collecting another run requires a separate decision.

## What we measure

### General skill development pilot

`config/skill_pilot.toml` tests the general conflict-resolution instruction in
`experiment/prompts.py`: five fresh development logs, C/R/RG/E, skill off/on,
one repeat (40 calls per model). The instruction is identical across versions
and uses no budget-specific examples. Prepared runs freeze and hash its exact text.

The historical run is `runs/skill_pilot_v1`, with **40 completed GPT responses**.
Its planned Claude portion was not collected. Inspect its descriptive results:

```bash
python -m experiment pilot-report runs/skill_pilot_v1
```

See the [saved pilot report](runs/skill_pilot_v1/analysis/pilot_report.txt).
Wrong answers are kept; any skill revision needs a new run directory. These seeds
must stay out of the main study.

This first pilot batch used the legacy generator. Later runs correct chronology;
the completed draft screen used five repeats for selection, and the current workflow pilot
uses ten repeats and `screen-report` for descriptive comparisons.
See `runs/skill_pilot_v1/PILOT_NOTES.md` for predictions and limitations. Use
`pilot-report` for the pilot; the older `analyze` comparisons below are not the v2 plan.

### Study outcomes

- **Accuracy:** Does the final `ANSWER` line match the answer key?
- **Failure type:** Does a wrong answer match a withdrawal, gossip, or arithmetic mistake? Distinctive dollar amounts help identify possible errors, though they cannot prove the model's reasoning. We also track missing answers and output cutoffs.
- **Consistency:** Across repeated calls with the same input, is each log always, sometimes, or never answered correctly? Does a consistently wrong answer stay the same? The latest pilot uses ten repeats per condition.

We compare versions and skill settings on the same logs, averaging repeats within
each log. The development reports are descriptive; the two-log results do not
include significance tests or confidence intervals intended to establish efficacy.

Two independent solvers must agree on every version. Validation also checks [hand-worked examples](data/hand_logs.json) and confirms the rendered text gives the expected answer.

## Running the experiment

Use **Python 3.11+** from the repository root. Start with local checks, these make no model calls:

```bash
pip install -r requirements.txt
python -m experiment validate
python -m experiment preview --seed 1 --records 40
```

`validate` checks the generator, solvers, and scoring. `preview` shows R and E side by side with an answer key and record explanations; use `--versions` to choose other versions.

For live runs, install and sign in to the **Claude Code and Codex CLIs** with subscriptions that can access the configured models. Then check access and prepare the pilot:

```bash
python -m experiment check
python -m experiment prepare config/trial.toml runs/trial_v1
```

`check` makes one small live call per model. `prepare` freezes logs, prompts, answer keys, settings, and call order without model calls.

```bash
python -m experiment collect runs/trial_v1
python -m experiment status runs/trial_v1
python -m experiment analyze runs/trial_v1
```

`collect` saves responses and call metadata. Each call uses a fresh session with tools and personal agent context disabled. Rerun it to resume. Select one model with `--models claude` or `--models gpt`, and share saved attempts through Git.

`status` shows progress. `analyze` writes CSV tables and a text report to `runs/<name>/analysis/`. Each command supports `--help`.

### What belongs in Git

Commit the code, skill drafts, configurations and protocols, frozen run inputs,
manifests, and recorded attempts. Text result reports (`*_report.txt`), failure
reviews (`*_failure_review.md`), and their supporting checkpoint audits
(`*_checkpoint_audit.csv`) are also included. Other generated analysis tables
and summaries remain ignored because the report commands can rebuild them.

Machine-local launcher state (`runs/*_job.json`), log files, live collection locks,
and temporary files are ignored. Do not remove or rewrite frozen run files to
update historical collection plans; use the run's development notes to record
stops and extensions.

## Limitations

These synthetic logs test performance under explicit budget rules. The distinctive amounts used to diagnose mistakes may also give models an unintended cue. Model identifiers do not pin a fixed checkpoint, so results may vary across collection dates.

## Repository guide

| Path                                       | Purpose                                                     |
| ------------------------------------------ | ----------------------------------------------------------- |
| [config/](config/)                         | Pilot and draft main-study settings                         |
| [data/hand_logs.json](data/hand_logs.json) | Worked examples for validation                              |
| [experiment/](experiment/)                 | Generator, solvers, prompts, clients, scoring, and analysis |
| `runs/<name>/`                             | Frozen inputs, recorded attempts, and generated analysis    |
