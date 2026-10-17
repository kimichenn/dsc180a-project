"""Shared infrastructure for every experiment in this folder; no experiment-specific logic lives here.

- prompts: the Prompt every client takes (system text + messages)
- models: model configs, API clients, credentials (.env)
- subscriptions: the same interface over the logged-in Claude Code and Codex CLIs
- calls: retries and the error that stops a run
- runs: responses.jsonl and manifest.json in a run directory, token counting
- answers, names: the ANSWER-line pattern and made-up project names
"""
