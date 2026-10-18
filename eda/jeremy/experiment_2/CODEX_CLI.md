# Start with Codex CLI

For generated questions, multiple models/efforts, automatic scoring, token tables,
and resumable batches, use [RUNNING.md](RUNNING.md). This page documents the
original one-example starter, which remains available for troubleshooting.

The starter runs one short, hand-checkable ledger through `codex exec` using your
ChatGPT sign-in. It checks the collection interface; it does not run the full
development or confirmation experiment.

From a terminal:

```bash
cd /Users/jeremycheng/Documents/dsc180a-project/eda/jeremy/experiment_2
bash run_codex_smoke.sh --check
bash run_codex_smoke.sh gpt-6-astra medium
```

The `--check` command verifies installation and ChatGPT sign-in without sending
a model request. If sign-in is missing, it prints the exact login command to run.
The starter requires ChatGPT sign-in and
removes API-key environment variables from its own process. Model availability
and usage remain subject to your subscription. If your chosen model or effort
is unavailable, inspect the saved error and choose an available configuration.
Keep the chosen model and effort fixed across a study's matched conditions.

The starter first looks for `codex` on your terminal's PATH, then automatically
checks this machine's app-bundled executable. Startup failures print their
diagnostics. You can also select an executable explicitly:

```bash
CODEX_BIN='/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex' \
  bash run_codex_smoke.sh gpt-6-astra medium
```

Each invocation creates a new directory under `results/codex_smoke_<timestamp>_*`:

| File | Contents |
|---|---|
| `prompt.txt` | Exact task prompt sent through standard input |
| `response.txt` | Final answer emitted by Codex |
| `events.jsonl` | Emitted run events, including reported usage and tool activity |
| `stderr.log` | CLI diagnostics and errors |
| `settings.txt` | CLI version, requested model/effort, timestamps, and exit status |
| `command.txt` | Exact CLI command, without credentials |

The expected answer is `{"route":"AMBER","approval_id":"R001"}`. It is not
included in the prompt. This example tests nested withdrawals; one success or
failure is not an accuracy estimate. If a run fails or hits a usage limit, retain
its logs. Running the starter again creates a new attempt instead of overwriting it.

The key CLI options are `--json` (event stream), `--output-last-message` (final
answer file), and `-` (read the prompt from stdin). A new `codex exec` invocation
starts a separate trial. Do not use `codex exec resume` to move between questions,
because that would carry earlier conversation context into the next question.

The starter uses an empty temporary working folder, skips user configuration,
sets the project-instruction byte limit to zero, and disables shell tools and
web search. It keeps Codex's own instructions and may still be affected by
managed settings or other available tools. Inspect the actual events; read-only
mode alone does not disable tools. The saved model name is the requested model,
not independent proof of an exact served checkpoint. This is a Codex-interface
test, and its results should be labeled accordingly.

The full batch collector now implements ledger generation, independent answer
solvers, condition scheduling, scoring, event validation, and resume tracking.
It also replaces the default model instruction file and disables additional
features; do not pool starter trials with its experiment results. This
starter does not enforce the protocol's proposed 32,000-token generation limit.

References: [Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode),
[authentication](https://learn.chatgpt.com/docs/auth), and
[configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
