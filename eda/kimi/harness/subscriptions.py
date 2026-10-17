"""Clients that run the official, logged-in CLIs, so calls bill to a subscription instead of an API key.

- claude-code: `claude -p` (Claude Code) on the Claude Pro/Max login.
- codex: `codex exec` (Codex CLI) on the ChatGPT login.

Gemini has no equivalent: Gemini CLI no longer accepts personal Google sign-in, and Antigravity
has no headless mode, so Gemini runs only on the API.

Both CLIs are coding agents, so each call is fenced off to behave like a plain API request:
our system prompt replaces the agent's, every tool is off, user customizations (CLAUDE.md,
AGENTS.md, skills, plugins, MCP servers, memories) are not loaded, the call runs in
an empty temporary folder, and API keys are stripped from its environment so it can never bill one.
A response that still used a tool is recorded with usage["tool_calls"] > 0. Claude Code also resumes a
response that hits the output limit (up to three times); those turns are usage["continuations"].
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from harness.models import Completion, ModelConfig
from harness.prompts import Prompt

TIMEOUT_S = 1800
# Anything that would route the CLI to an API key (and bill it), or mark it as nested in another Claude Code.
_BILLING_ENV = re.compile(r"^(ANTHROPIC_|OPENAI_|CODEX_API_KEY$|CLAUDE_CODE_USE_|CLAUDECODE$|CLAUDE_CODE_ENTRYPOINT$|CLAUDE_CODE_SSE_PORT$)")
_AUTH_HINTS = ("not logged in", "/login", "codex login", "invalid api key", "unauthorized", "401")
_MODEL_HINTS = ("model_not_found", "does not exist", "unknown model", "invalid model", "not supported")
_LIMIT_HINTS = ("usage limit", "session limit", "rate limit", "limit reached", "hit your", "quota", "429")


class SubscriptionError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code  # 4xx makes harness.models.is_fatal stop the run


def _error(provider: str, message: str) -> SubscriptionError:
    text = " ".join(message.split())[:400]
    low = text.lower()
    if any(hint in low for hint in _AUTH_HINTS):
        return SubscriptionError(f"{provider}: not logged in: {text}", 401)
    if any(hint in low for hint in _MODEL_HINTS):
        return SubscriptionError(f"{provider}: model unavailable on this plan: {text}", 400)
    if any(hint in low for hint in _LIMIT_HINTS):
        return SubscriptionError(f"{provider}: subscription usage limit reached, rerun later: {text}")
    return SubscriptionError(f"{provider}: {text}")


def _environment(**extra: str) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not _BILLING_ENV.match(key)}
    env.update(extra)
    return env


def _user_text(prompt: Prompt) -> str:
    if len(prompt.messages) != 1 or prompt.messages[0]["role"] != "user":
        raise ValueError("subscription CLIs take a single user message; multi-turn prompts need an API provider")
    return prompt.messages[0]["content"]


def _run(provider: str, cmd: list[str], stdin: str, cwd: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, input=stdin, capture_output=True, text=True, cwd=cwd, env=env, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise SubscriptionError(f"{provider}: no response after {TIMEOUT_S}s") from None


def _version(binary: str) -> str:
    return subprocess.run([binary, "--version"], capture_output=True, text=True).stdout.strip()


def _toml(value) -> str:
    """A -c override value: TOML booleans, quoted strings, and inline tables."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ",".join(_toml(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(f"{k}={_toml(v)}" for k, v in value.items()) + "}"
    return str(value)


class ClaudeCodeClient:
    def __init__(self, config: ModelConfig):
        self.config = config
        self.binary = shutil.which("claude")
        if self.binary is None:
            raise ValueError("claude-code: the `claude` CLI is not on PATH; install Claude Code and log in")
        self.version = _version(self.binary)

    def generate(self, prompt: Prompt) -> Completion:
        c = self.config
        # --safe-mode skips CLAUDE.md, skills, plugins, hooks, and MCP servers but keeps the subscription login
        # (--bare would skip the login too). --tools "" leaves the model no tools at all.
        cmd = [
            self.binary, "-p", "--safe-mode", "--model", c.model, "--system-prompt", prompt.system,
            "--tools", "", "--strict-mcp-config", "--no-session-persistence", "--output-format", "json",
        ]
        if c.reasoning:
            cmd += ["--effort", c.reasoning]
        env = _environment(CLAUDE_CODE_MAX_OUTPUT_TOKENS=str(c.max_output_tokens))
        with tempfile.TemporaryDirectory(prefix="claude-call-") as cwd:
            done = _run("claude-code", cmd, _user_text(prompt), cwd, env)
        try:
            data = json.loads(done.stdout)
        except json.JSONDecodeError:
            raise _error("claude-code", done.stderr or done.stdout or f"exit {done.returncode}") from None
        if data.get("is_error") or done.returncode:
            raise _error("claude-code", str(data.get("result") or done.stderr or data.get("subtype")))
        usage = dict(data.get("usage") or {})
        usage["tool_calls"] = 0  # --tools "" leaves none; a second turn is Claude Code resuming past the output limit
        usage["continuations"] = max(0, (data.get("num_turns") or 1) - 1)
        usage["api_equivalent_usd"] = data.get("total_cost_usd")  # what Claude Code reports; not billed
        # modelUsage can include Claude Code's own background calls; the answer comes from the requested model.
        served = data.get("modelUsage") or {}
        usage["served_models"] = sorted(served)
        model = c.model if c.model in served else max(served, key=lambda m: served[m].get("outputTokens") or 0, default=None)
        return Completion(data.get("result") or "", data.get("stop_reason") or data.get("subtype"), model, usage)


# Codex adds agent context from several places; each setting below removes one (checked with
# `codex debug prompt-input`: with all of them the model sees only our instructions and the user message).
_CODEX_FEATURES_OFF = (
    "shell_tool", "unified_exec", "multi_agent", "multi_agent_v2", "plugins", "apps", "tool_suggest", "skill_search",
    "browser_use", "computer_use", "image_generation", "view_image", "code_mode_host", "sleep_tool", "goals",
)
_CODEX_SETTINGS = {
    "include_permissions_instructions": False,
    "include_environment_context": False,
    "include_apps_instructions": False,
    "include_collaboration_mode_instructions": False,
    "web_search": "disabled",
    "forced_login_method": "chatgpt",
}
# Model-catalog fields that add multi-agent instructions, a JavaScript runner ("tool_mode":
# "code_mode_only", ~2K tokens of tool definitions), or the apply_patch tool. Without them the
# request carries only request_user_input, which cannot be answered in `codex exec`.
_CATALOG_DROP = ("tool_mode",)
_CATALOG_PATCH = {
    "multi_agent_version": None, "node_repl_disabled": True, "experimental_supported_tools": [],
    "supports_search_tool": False, "apply_patch_tool_type": None,
}
_NOT_TOOLS = ("agent_message", "reasoning", "error")


def _find_codex() -> str:
    found = os.environ.get("CODEX_BIN") or shutil.which("codex")
    if found:
        return found
    bundled = sorted(Path.home().glob(".vscode/extensions/openai.chatgpt-*/bin/*/codex")) + sorted(Path("/Applications").glob("Codex.app/Contents/Resources/codex"))
    if not bundled:
        raise ValueError("codex: no `codex` CLI on PATH or in the VS Code extension; install it or set CODEX_BIN")
    return str(bundled[-1])


class CodexClient:
    def __init__(self, config: ModelConfig):
        self.config = config
        self.binary = _find_codex()
        self.version = _version(self.binary)
        self.codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        auth_file = self.codex_home / "auth.json"
        auth = json.loads(auth_file.read_text()) if auth_file.exists() else {}
        if auth.get("auth_mode") != "chatgpt":
            raise ValueError(f"codex: {auth_file} is not a ChatGPT login; run `codex login` and sign in with ChatGPT")
        catalog_file = self.codex_home / "models_cache.json"
        models = json.loads(catalog_file.read_text()).get("models", []) if catalog_file.exists() else []
        entry = next((m for m in models if m.get("slug") == config.model), None)
        if entry is None:
            raise ValueError(f"codex: {config.model} is not in {catalog_file}; open Codex once to refresh it, or pick another model")

        # An empty HOME hides ~/.agents/skills; CODEX_HOME still points at the real login.
        self._dir = Path(tempfile.mkdtemp(prefix="codex-isolated-"))
        atexit.register(shutil.rmtree, self._dir, True)
        (self._dir / "home").mkdir()
        catalog = self._dir / "catalog.json"
        kept = {key: value for key, value in entry.items() if key not in _CATALOG_DROP}
        catalog.write_text(json.dumps({"models": [{**kept, **_CATALOG_PATCH}]}))
        skills = {str(p) for p in self.codex_home.glob("skills/**/SKILL.md")} | {str(p) for p in self.codex_home.glob("skills/.system/*/SKILL.md")}
        settings = {**_CODEX_SETTINGS, "model_catalog_json": str(catalog)}
        if config.reasoning:
            settings["model_reasoning_effort"] = config.reasoning
        if entry.get("support_verbosity"):
            settings["model_verbosity"] = "medium"  # the API default; Codex's own default is low
        self._overrides = [arg for key, value in settings.items() for arg in ("-c", f"{key}={_toml(value)}")]
        if skills:
            self._overrides += ["-c", "skills.config=" + _toml([{"path": p, "enabled": False} for p in sorted(skills)])]
        self._overrides += [arg for feature in _CODEX_FEATURES_OFF for arg in ("--disable", feature)]

    def _instructions(self, system: str) -> Path:
        path = self._dir / f"instructions-{hashlib.sha1(system.encode()).hexdigest()[:12]}.md"
        if not path.exists():
            path.write_text(system)
        return path

    def generate(self, prompt: Prompt) -> Completion:
        c = self.config
        instructions = self._instructions(prompt.system)
        env = _environment(HOME=str(self._dir / "home"), CODEX_HOME=str(self.codex_home))
        with tempfile.TemporaryDirectory(prefix="call-", dir=self._dir) as cwd:
            cmd = [
                self.binary, "exec", "--json", "--ephemeral", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules",
                "--sandbox", "read-only", "-C", cwd, "-m", c.model, *self._overrides,
                "-c", f"model_instructions_file={_toml(str(instructions))}", "-",
            ]
            done = _run("codex", cmd, _user_text(prompt), cwd, env)
        texts, errors, usage, tools = [], [], None, 0
        for line in done.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = event.get("type")
            if kind == "item.completed":
                item = event.get("item") or {}
                if item.get("type") == "agent_message":
                    texts.append(item.get("text") or "")
                elif item.get("type") not in _NOT_TOOLS:
                    tools += 1
            elif kind == "turn.completed":
                usage = dict(event.get("usage") or {})
            elif kind in ("turn.failed", "error"):
                errors.append(str((event.get("error") or {}).get("message") or event.get("message") or event))
        if usage is None:
            raise _error("codex", " | ".join(errors) or done.stderr or f"exit {done.returncode}")
        usage["tool_calls"] = tools
        return Completion(texts[-1] if texts else "", "completed", None, usage)

