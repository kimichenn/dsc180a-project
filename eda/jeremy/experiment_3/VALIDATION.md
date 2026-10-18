# Validation before collection

Validated on 2026-10-18 UTC. No live model requests were made during preparation.

- All **20 offline tests passed**, including hand-computed cases, exhaustive small withdrawal graphs, 100 generated worlds with all four controls, the five full-size development worlds, strict terminal scoring, resumable collection, usage accounting, retries, timeouts, locks, and interface exclusions.
- The two independent solvers agree on every saved smoke and development answer in every generated condition.
- `results/smoke_v1` has **5 planned Astra-medium trials and 0 attempts** at preparation.
- `results/flagship_dense_v1` has **90 planned trials and 0 attempts** at preparation: five worlds × two conditions × three models × three supported reasoning levels. Every model/effort cell has five clean and five conflict trials.
- The final task-plus-policy estimates span **58,588–59,530 tokens** for the scheduled development prompts. Counts are character-based estimates and exclude additional CLI context. Within-world estimated condition matching passes the 2% tolerance; actual model-token matching is unverified.
- Current CLI preflight passed: `codex-cli 0.162.0-alpha.17.2`, signed in through ChatGPT. This is a local interface/login check, not confirmation of live access to each model.
- New run manifest, artifact, and source hashes were verified. Experiment 2 source hashes still match its `development_v1`, `development_depth16_v1`, and `confirmation_luna_high_v1` manifests.

The live smoke run is still required to verify the new task's response format in Codex. The development run has no measured accuracy or token usage yet. See [the collection guide](README.md) for the commands and decision rules.
