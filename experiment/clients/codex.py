"""GPT through `codex exec` (Codex CLI) on the ChatGPT login.

Codex adds agent context from several places; each setting below removes one (checked with
`codex debug prompt-input`: with all of them the model sees only our instructions and the user
message, plus one tool, request_user_input, that `codex exec` cannot answer). The JSON event
stream is then audited. Anything but one fresh turn with no error events, from the requested model,
is a harness failure; a tool item is the model's own doing, so it is flagged and the call still counts.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import shutil
import tempfile
from collections import Counter
from pathlib import Path

from experiment.clients.base import Completion, FatalClientError, classify_error, cli_version, environment, run_cli
from experiment.config import ModelSpec
from experiment.prompts import Prompt

_FEATURES_OFF = (
    "shell_tool", "unified_exec", "multi_agent", "multi_agent_v2", "plugins", "apps", "tool_suggest", "skill_search",
    "browser_use", "computer_use", "image_generation", "view_image", "code_mode_host", "sleep_tool", "goals",
)
_SETTINGS = {
    "include_permissions_instructions": False,
    "include_environment_context": False,
    "include_apps_instructions": False,
    "include_collaboration_mode_instructions": False,
    "web_search": "disabled",
    "forced_login_method": "chatgpt",
}
# Model-catalog fields that add multi-agent instructions, a JavaScript runner ("tool_mode":
# "code_mode_only", ~2K tokens of tool definitions), or the apply_patch tool.
_CATALOG_DROP = ("tool_mode",)
_CATALOG_PATCH = {
    "multi_agent_version": None, "node_repl_disabled": True, "experimental_supported_tools": [],
    "supports_search_tool": False, "apply_patch_tool_type": None,
}
_NOT_TOOLS = ("agent_message", "reasoning", "error")
_KNOWN_EVENTS = {"thread.started", "turn.started", "turn.completed", "turn.failed", "error", "item.started", "item.updated", "item.completed"}
# Where Codex installs itself besides PATH: the VS Code extension, the Codex app, and the ChatGPT app.
_INSTALLS = (
    ".vscode/extensions/openai.chatgpt-*/bin/*/codex",
    "/Applications/Codex.app/Contents/Resources/codex",
    "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex",
)


def find_codex() -> str:
    found = os.environ.get("CODEX_BIN") or shutil.which("codex")
    if found:
        return found
    for pattern in _INSTALLS:
        root, pattern = (Path("/"), pattern[1:]) if pattern.startswith("/") else (Path.home(), pattern)
        matches = sorted(root.glob(pattern))
        if matches:
            return str(matches[-1])
    raise FatalClientError("codex: no `codex` CLI on PATH or in the VS Code extension, Codex app, or ChatGPT app; set CODEX_BIN")


def _toml(value) -> str:
    """A -c override value: TOML booleans, quoted strings, lists, and inline tables."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ",".join(_toml(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(f"{k}={_toml(v)}" for k, v in value.items()) + "}"
    return str(value)


class CodexClient:
    def __init__(self, spec: ModelSpec):
        self.spec = spec
        self.binary = find_codex()
        self.version = cli_version(self.binary)
        self.codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        auth_file = self.codex_home / "auth.json"
        auth = json.loads(auth_file.read_text()) if auth_file.exists() else {}
        if auth.get("auth_mode") != "chatgpt":
            raise FatalClientError(f"codex: {auth_file} is not a ChatGPT login; run `codex login` and sign in with ChatGPT")
        catalog_file = self.codex_home / "models_cache.json"
        models = json.loads(catalog_file.read_text()).get("models", []) if catalog_file.exists() else []
        entry = next((m for m in models if m.get("slug") == spec.model), None)
        if entry is None:
            raise FatalClientError(f"codex: {spec.model} is not in {catalog_file}; open Codex once to refresh it")
        efforts = [e["effort"] if isinstance(e, dict) else e for e in entry.get("supported_reasoning_levels", [])]
        if efforts and spec.effort not in efforts:
            raise FatalClientError(f"codex: {spec.model} does not offer effort {spec.effort!r} (offers {', '.join(efforts)})")

        # An empty HOME hides ~/.agents/skills; CODEX_HOME still points at the real login.
        self._dir = Path(tempfile.mkdtemp(prefix="experiment-codex-"))
        atexit.register(shutil.rmtree, self._dir, True)
        (self._dir / "home").mkdir()
        catalog = self._dir / "catalog.json"
        kept = {key: value for key, value in entry.items() if key not in _CATALOG_DROP}
        catalog.write_text(json.dumps({"models": [{**kept, **_CATALOG_PATCH}]}))
        settings = {**_SETTINGS, "model_catalog_json": str(catalog), "model_reasoning_effort": spec.effort}
        if entry.get("support_verbosity"):
            settings["model_verbosity"] = "medium"  # the API default; Codex's own default is low
        self._overrides = [arg for key, value in settings.items() for arg in ("-c", f"{key}={_toml(value)}")]
        skills = sorted({str(p) for pattern in ("skills/**/SKILL.md", "skills/.system/*/SKILL.md") for p in self.codex_home.glob(pattern)})
        if skills:
            self._overrides += ["-c", "skills.config=" + _toml([{"path": p, "enabled": False} for p in skills])]
        self._overrides += [arg for feature in _FEATURES_OFF for arg in ("--disable", feature)]

    def _instructions(self, system: str) -> Path:
        path = self._dir / f"instructions-{hashlib.sha1(system.encode()).hexdigest()[:12]}.md"
        if not path.exists():
            path.write_text(system)
        return path

    def complete(self, prompt: Prompt, timeout: int) -> Completion:
        s = self.spec
        env = environment(HOME=str(self._dir / "home"), CODEX_HOME=str(self.codex_home))
        with tempfile.TemporaryDirectory(prefix="call-", dir=self._dir) as cwd:
            cmd = [
                self.binary, "exec", "--json", "--ephemeral", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules",
                "--sandbox", "read-only", "-C", cwd, "-m", s.model, *self._overrides,
                "-c", f"model_instructions_file={_toml(str(self._instructions(prompt.system)))}", "-",
            ]
            code, stdout, stderr = run_cli("codex", cmd, prompt.user, cwd, env, timeout)

        events, unreadable = [], 0
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                unreadable += 1
                continue
            if isinstance(event, dict):
                events.append(event)
        counts = Counter(e.get("type") for e in events)
        items = [e["item"] for e in events if e.get("type") == "item.completed" and isinstance(e.get("item"), dict)]
        messages = [item.get("text") or "" for item in items if item.get("type") == "agent_message"]
        errors = [str((e.get("error") or {}).get("message") or e.get("message") or e) for e in events if e.get("type") in ("turn.failed", "error")]
        completed = [e for e in events if e.get("type") == "turn.completed"]
        if not completed:
            raise classify_error("codex", " | ".join(errors) or stderr or f"exit {code}")

        reported = completed[-1].get("usage") or {}
        usage = {key: reported.get(key) for key in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")}
        tools = sorted({item.get("type", "unknown") for item in items if item.get("type") not in _NOT_TOOLS})
        served = sorted({e["model"] for e in events if isinstance(e.get("model"), str)})
        flags = [f"used a tool ({', '.join(tools)})"] if tools else []
        harness = []
        if counts["thread.started"] != 1 or counts["turn.started"] != 1 or counts["turn.completed"] != 1:
            harness.append("not exactly one fresh turn")
        if errors:
            harness.append("error events: " + " | ".join(errors)[:300])
        if unreadable or set(counts) - _KNOWN_EVENTS:
            harness.append("unexpected event stream")
        if served and served != [s.model]:
            harness.append(f"served {', '.join(served)}")
        thread = next((e.get("thread_id") for e in events if e.get("type") == "thread.started"), None)
        raw = {"events": events, "stderr_tail": stderr[-2000:]}
        return Completion(messages[-1] if messages else "", usage, served[0] if len(served) == 1 else None, "completed", thread,
                          harness, flags, raw)
