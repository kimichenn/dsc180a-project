"""The budget-ledger experiment: generate logs with gossip and withdrawals, call models through their
CLIs, and score each answer's status and the error signatures a wrong number matches.

Pipeline: config/*.toml -> generator (worlds, their versions, answer keys) -> runs.prepare (frozen
prompts and call schedule) -> collect (Claude Code and Codex clients) -> scoring -> analysis.
Run `python -m experiment --help` from the repository root.
"""
