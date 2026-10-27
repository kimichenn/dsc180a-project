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

We plan to compare **Claude Opus 5.5 and GPT-6 Astra** at **1,600 records per log**.

- **Pilot:** [config/trial.toml](config/trial.toml) checks the setup and repeatability on five logs, with and without the skill (**48 calls per model**). Pilot data are kept separate from the main study.
- **Main study:** [config/main.toml](config/main.toml) uses 30 new logs, all four versions, skill off/on, and three repeats. Ten randomly selected logs get additional repeats in R and RG, reaching ten repeats (**1,000 calls per model** in total).

The archived `runs/trial_v1` uses an older run format (code at commit `043da3e`).

## What we measure

- **Accuracy:** Does the final `ANSWER` line match the answer key? Missing answers count as wrong.
- **Error signatures:** Do wrong numbers match patterns associated with withdrawal, gossip, or arithmetic mistakes? These matches suggest possible errors but cannot prove the model's reasoning.
- **Repeatability:** How often do repeated prompts produce the same answer, and is that answer correct?

We compare versions and skill settings on the same logs, using the first three repeats for accuracy comparisons and reporting 95% confidence intervals. Extra repeats are used only to describe repeatability.

Two independent solvers must agree on every version. Validation also checks [hand-worked examples](data/hand_logs.json) and confirms the rendered text gives the expected answer.

## Running the experiment

Use **Python 3.11+** from the repository root. Start with local checks, these make no model calls:

```bash
pip install -r requirements.txt
python -m experiment validate
python -m experiment preview --seed 1 --records 40
```

`validate` checks the generator, solvers, and scoring. `preview` shows R and E side by side with an answer key and record explanations; use `--versions` to choose other versions.

For live runs, install and sign in to the **Claude Code and Codex CLIs** with subscriptions that can access the configured models. The `skill` arm loads Workflow V2 from [experiment/skills/workflow_v2.md](experiment/skills/workflow_v2.md) through [experiment/prompts.py](experiment/prompts.py). Preparing the main study also requires a clean, committed working tree.

Check access and prepare the pilot:

```bash
python -m experiment check
python -m experiment prepare config/trial.toml runs/trial_v2
```

`check` makes one small live call per model. `prepare` freezes logs, prompts, answer keys, settings, and call order without model calls.

```bash
python -m experiment collect runs/trial_v2
python -m experiment status runs/trial_v2
python -m experiment analyze runs/trial_v2
```

`collect` saves responses and call metadata, using a fresh session with tools and personal agent context disabled for each call. Rerun it to resume; failed calls get up to three attempts, while completed valid responses are kept regardless of correctness. Select one model with `--models claude` or `--models gpt`, and share saved attempts through Git.

`status` shows progress. `analyze` writes CSV tables and a text report to `runs/<name>/analysis/`. Each command supports `--help`.

## Limitations

These synthetic logs test performance under explicit budget rules. The distinctive amounts used to diagnose mistakes may also give models an unintended cue. Model identifiers do not pin a fixed checkpoint, so results may vary across collection dates.

## Repository guide

| Path                                       | Purpose                                                     |
| ------------------------------------------ | ----------------------------------------------------------- |
| [config/](config/)                         | Pilot and main-study settings                               |
| [data/hand_logs.json](data/hand_logs.json) | Worked examples for validation                              |
| [experiment/](experiment/)                 | Generator, solvers, prompts, clients, scoring, and analysis |
| `runs/<name>/`                             | Frozen inputs, recorded attempts, and generated analysis    |
