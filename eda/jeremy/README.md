# Jeremy's EDA experiments

Each experiment keeps its design, code, data, and results together.

| Experiment | Study | Status |
|---|---|---|
| [Experiment 1](experiment_1/README.md) | Misleading context and a conflict-resolution skill with Qwen3-1.7B and Qwen3-4B | Completed pilot and evaluation |
| [Experiment 2](experiment_2/README.md) | Revoked evidence and misleading summaries across GPT models and reasoning levels | Development collected through depth 16; Luna confirmation plan prepared |
| [Experiment 3](experiment_3/README.md) | Dense cumulative budgets with nested withdrawals and misleading messages | Flagship development screen prepared for Astra and both Sol models |

```text
experiment_1/
  README.md          Study instructions and commands
  eda.py, eda.ipynb   Analysis and collection
  study.py           Shared helpers for this experiment
  config.json        Model and generation settings
  skill.md           Conflict-resolution instructions
  data/              Questions and generator
  results/           Completed pilot_v1 and evaluation_v1 runs
  runs/              Original notebook run manifest
  tests/             Offline checks
experiment_2/
  README.md          Experiment protocol and analysis plan
  RUNNING.md         Batch collection commands and saved outputs
  config.json       Models, reasoning levels, and stage settings
  run.py            Prepare, collect, resume, and analyze
  ledger.py         Generator and independent answer solvers
  planning.py       Frozen questions and randomized schedule
  collection.py     Codex execution, event audit, scoring, token reports
  instructions/     Common, neutral, and skill instructions
  tests/            Offline checks with temporary fixtures
  results/          Frozen runs and saved attempts
  CODEX_CLI.md       Original one-example starter instructions
experiment_3/
  README.md          Flagship stress-test design and collection commands
  config.json        Fresh seeds, model/effort matrix, and decision rules
  run.py            Prepare, collect, resume, and analyze
  ledger.py         Dense budget generator, two solvers, terminal-answer checker
  planning.py       Frozen questions and randomized schedule
  collection.py     Saved responses, event audits, scores, input/output tokens
  tests/            Answer-key and offline collection checks
  results/          Separate smoke and flagship development plans
```

Start with Experiment 1's [evaluation report](experiment_1/results/evaluation_v1/results_v1.md)
or its [generated findings](experiment_1/results/evaluation_v1/findings.md).

From the repository root, analyze the saved evaluation with:

```bash
python eda/jeremy/experiment_1/eda.py --phase evaluation
```

Future studies should use `experiment_4/`, `experiment_5/`, and so on, with their
own `README.md` and, when implemented, `data/` and `results/` folders.
The existing `.venv` link in this folder remains available as a shared local environment.
