# Resolving Conflicting Records in Long-Context Language Models

This **DSC 180A capstone** tests whether language models can work out a project's current budget from a long log of updates, false claims, and canceled changes. We generate synthetic logs with known answers to compare how models handle each kind of conflict.

We ask three questions:

1. Do models fail because they trust false claims, miss canceled updates, or both?
2. Can a **conflict-resolution skill** (a written guide added to the prompt) reduce those failures without hurting accuracy on clean logs?
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

The answer is **$810K**: $800K − $15K + $25K. The Engineering claim does not count, and #005 cancels the $40K increase in #003.

## Experimental design

Exploratory runs suggest withdrawals cause more trouble than gossip. We test this using four versions of each log:

| Version             | Gossip | Withdrawals, including withdrawals of withdrawals |
| ------------------- | ------ | ------------------------------------------------- |
| C: clean            | No     | No                                                |
| G: gossip only      | Yes    | No                                                |
| R: withdrawals only | No     | Yes                                               |
| RG: both            | Yes    | Yes                                               |

All four have **the same correct answer and number of records**, with similar text lengths. Excluded records become harmless filler; removing withdrawals also removes the Finance changes they ultimately cancel. This lets us isolate the effect of each conflict type.

We wish to compare **Claude Opus 5.5 and GPT-6 Astra** at **1,600 records per log**, starting at low reasoning effort.

- **Pilot:** [config/trial.toml](config/trial.toml) uses five throwaway logs to check difficulty and timing. A model scoring below 4/5 on clean logs will move to medium effort before the main run.
- **Main study:** The planned design is 20 new logs \* 4 versions \* 2 instruction settings (skill off/on) \* 3 repeats = **480 calls per model**. The skill must improve conflict handling without lowering the accuracy for the clean version.

## What we measure

- **Accuracy:** Does the final `ANSWER` line match the answer key?
- **Failure type:** Does a wrong number match counting gossip, missing a withdrawal, or dropping a restored update? Distinctive dollar amounts help identify possible mistakes, though they cannot prove the model's reasoning. We also track other errors, missing answers, and output cutoffs.
- **Consistency:** Across three repeats, is each log always, sometimes, or never answered correctly? Does a consistently wrong answer stay the same?

We average repeats within each log, then compare versions on the same logs with 95% bootstrap confidence intervals.

Two independent solvers must agree on every version. Validation also checks [hand-worked examples](data/hand_logs.json) and confirms the rendered text gives the expected answer.

## Running the experiment

Use **Python 3.11+** from the repository root. Start with local checks, these make no model calls:

```bash
pip install -r requirements.txt
python -m experiment validate
python -m experiment preview --seed 1 --records 40
```

`validate` checks the generator, solvers, and scoring. `preview` prints a small log, its answer key, and an explanation of each record.

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

## Limitations

These synthetic logs test performance under explicit budget rules. The distinctive amounts used to diagnose mistakes may also give models an unintended cue. Model identifiers do not pin a fixed checkpoint, so results may vary across collection dates.

## Repository guide

| Path                                       | Purpose                                                     |
| ------------------------------------------ | ----------------------------------------------------------- |
| [config/](config/)                         | Pilot and draft main-study settings                         |
| [data/hand_logs.json](data/hand_logs.json) | Worked examples for validation                              |
| [experiment/](experiment/)                 | Generator, solvers, prompts, clients, scoring, and analysis |
| `runs/<name>/`                             | Frozen inputs, recorded attempts, and generated analysis    |
