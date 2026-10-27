"""Claude through `claude -p` (Claude Code) on the Claude Pro/Max login."""

from __future__ import annotations

import json
import shutil
import tempfile

from experiment.clients.base import Completion, FatalClientError, classify_error, cli_version, environment, run_cli
from experiment.config import ModelSpec
from experiment.prompts import Prompt


class ClaudeCodeClient:
    def __init__(self, spec: ModelSpec):
        self.spec = spec
        binary = shutil.which("claude")
        if binary is None:
            raise FatalClientError("claude-code: the `claude` CLI is not on PATH; install Claude Code and log in")
        self.binary = binary
        self.version = cli_version(binary)

    def complete(self, prompt: Prompt, timeout: int) -> Completion:
        s = self.spec
        # --safe-mode skips CLAUDE.md, skills, plugins, hooks, and MCP servers but keeps the subscription
        # login (--bare would skip the login too). --tools "" leaves the model no tools at all.
        cmd = [
            self.binary, "-p", "--safe-mode", "--model", s.model, "--effort", s.effort, "--system-prompt", prompt.system,
            "--tools", "", "--strict-mcp-config", "--no-session-persistence", "--output-format", "json",
        ]
        env = environment(CLAUDE_CODE_MAX_OUTPUT_TOKENS=str(s.max_output_tokens))
        with tempfile.TemporaryDirectory(prefix="experiment-claude-") as cwd:
            code, stdout, stderr = run_cli("claude-code", cmd, prompt.user, cwd, env, timeout)
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            raise classify_error("claude-code", stderr or stdout or f"exit {code}") from None
        if data.get("is_error") or code:
            raise classify_error("claude-code", str(data.get("result") or stderr or data.get("subtype")))

        reported = data.get("usage") or {}
        # Claude counts cache reads and writes apart from input_tokens.
        cached = reported.get("cache_read_input_tokens") or 0
        written = reported.get("cache_creation_input_tokens") or 0
        usage = {
            "input_tokens": (reported.get("input_tokens") or 0) + cached + written,
            "cached_input_tokens": cached,
            "output_tokens": reported.get("output_tokens"),
            "reasoning_output_tokens": None,  # included in output_tokens; not reported apart
            # More than one turn means Claude Code resumed a response that hit the output limit.
            "turns": data.get("num_turns"),
        }
        # modelUsage can include Claude Code's own background calls; the answer comes from the requested model.
        served = data.get("modelUsage") or {}
        model = s.model if s.model in served else max(served, key=lambda m: served[m].get("outputTokens") or 0, default=None)
        audit = [] if model in (None, s.model) else [f"served {model}"]
        raw = {key: value for key, value in data.items() if key != "result"}
        return Completion(data.get("result") or "", usage, model, data.get("stop_reason") or data.get("subtype"), audit, raw)
