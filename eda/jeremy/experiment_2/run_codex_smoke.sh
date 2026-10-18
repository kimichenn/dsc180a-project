#!/usr/bin/env bash
# One CLI plumbing check. This is not the full Experiment 2 collector.
set -euo pipefail

check_only=false
if [[ "${1:-}" == "--check" ]]; then
  check_only=true
  shift
  if [[ $# -ne 0 ]]; then
    printf '%s\n' '--check does not take model arguments.' >&2
    exit 2
  fi
fi

if [[ "$check_only" == false && ( $# -eq 0 || "${1:-}" == "--help" ) ]]; then
  printf '%s\n' 'Usage: bash run_codex_smoke.sh MODEL [EFFORT]' \
    'Example: bash run_codex_smoke.sh gpt-6-astra medium' \
    'Check installation and login only: bash run_codex_smoke.sh --check' \
    'Runs one short ledger with ChatGPT sign-in and saves a new results folder.'
  exit 0
fi
if [[ $# -gt 2 ]]; then
  printf '%s\n' 'Expected a model ID and optionally a reasoning effort.' >&2
  exit 2
fi

model="${1:-}"
effort="${2:-medium}"
case "$effort" in
  low|medium|high|xhigh|max|ultra) ;;
  *) printf '%s\n' 'Choose an effort supported by your selected model.' >&2; exit 2 ;;
esac

experiment_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
codex_bin="${CODEX_BIN:-}"
if [[ -z "$codex_bin" ]]; then
  codex_bin="$(command -v codex || true)"
  if [[ -z "$codex_bin" && -x /Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex ]]; then
    codex_bin='/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex'
  fi
fi
if [[ -z "$codex_bin" ]] || ! command -v "$codex_bin" >/dev/null 2>&1; then
  printf 'Codex could not be found: %s\n' "${codex_bin:-not installed or not on PATH}" >&2
  printf '%s\n' 'Set CODEX_BIN to the full path of your Codex executable.' >&2
  exit 127
fi
printf 'Using Codex: %s\n' "$codex_bin"
# The CLI must use the ChatGPT login instead of an API credential from the shell.
unset OPENAI_API_KEY CODEX_API_KEY CODEX_AUTH_TOKEN
if login_status="$("$codex_bin" login status 2>&1)"; then
  :
else
  login_exit=$?
  printf 'Codex login check failed (exit %s):\n%s\n' "$login_exit" "$login_status" >&2
  printf 'Sign in with ChatGPT by running: %q login\n' "$codex_bin" >&2
  exit "$login_exit"
fi
case "$login_status" in
  *'Logged in using ChatGPT'*) ;;
  *) printf '%s\n' "$login_status" >&2
     printf 'Sign in with ChatGPT by running: %q login\n' "$codex_bin" >&2
     exit 1 ;;
esac
if cli_version="$("$codex_bin" --version 2>&1)"; then
  :
else
  version_exit=$?
  printf 'Codex version check failed (exit %s):\n%s\n' "$version_exit" "$cli_version" >&2
  exit "$version_exit"
fi
printf '%s\n' 'ChatGPT sign-in confirmed.'
if [[ "$check_only" == true ]]; then
  printf '%s\n' "$cli_version" 'Setup check passed. No model request was sent.'
  exit 0
fi

mkdir -p "$experiment_dir/results"
run_dir="$(mktemp -d "$experiment_dir/results/codex_smoke_$(date -u +%Y%m%dT%H%M%SZ)_XXXXXX")"
work_dir="$(mktemp -d "${TMPDIR:-/tmp}/eda-codex-XXXXXX")"
trap 'rmdir "$work_dir" 2>/dev/null || true' EXIT
cp "$experiment_dir/smoke_prompt.txt" "$run_dir/prompt.txt"
printf '%s\n' "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "cli_version=$cli_version" 'authentication=ChatGPT' \
  "requested_model=$model" "requested_reasoning_effort=$effort" \
  'purpose=CLI smoke test; not confirmation data' > "$run_dir/settings.txt"

command=("$codex_bin" exec --json --ephemeral --ignore-user-config
  --skip-git-repo-check --sandbox read-only --cd "$work_dir"
  --model "$model"
  -c 'forced_login_method="chatgpt"'
  -c "model_reasoning_effort=\"$effort\""
  -c 'project_doc_max_bytes=0'
  -c 'web_search="disabled"'
  -c 'features.shell_tool=false'
  -c 'features.remote_plugin=false'
  --output-last-message "$run_dir/response.txt" -)
printf '%q ' "${command[@]}" > "$run_dir/command.txt"
printf '\n' >> "$run_dir/command.txt"
printf 'Saving this trial to: %s\n' "$run_dir"

exit_status=0
"${command[@]}" < "$run_dir/prompt.txt" > "$run_dir/events.jsonl" \
  2> "$run_dir/stderr.log" || exit_status=$?
printf '%s\n' "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "exit_status=$exit_status" >> "$run_dir/settings.txt"

if [[ "$exit_status" -ne 0 ]]; then
  printf 'Codex exited with status %s. Details: %s/stderr.log\n' "$exit_status" "$run_dir" >&2
  exit "$exit_status"
fi
if [[ ! -s "$run_dir/response.txt" ]]; then
  printf 'No final answer was saved. Inspect %s/events.jsonl\n' "$run_dir" >&2
  exit 1
fi
printf '\nSaved response:\n'
cat "$run_dir/response.txt"
printf '\nExpected answer: {"route":"AMBER","approval_id":"R001"}\n'
printf '%s\n' 'Check events.jsonl for tool calls or failed turns before treating the response as usable.'
