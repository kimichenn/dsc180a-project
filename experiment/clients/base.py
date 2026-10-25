"""What every client shares: the Completion it returns, its errors, and a fenced-off CLI call.

Both CLIs are coding agents, so each call is fenced off to act like a plain model request: our
system prompt replaces the agent's, no tools, no user customizations (CLAUDE.md, AGENTS.md,
skills, plugins, MCP servers, memories), an empty temporary folder, no saved session, and an
environment with API keys removed so a call can only bill the logged-in subscription.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Protocol

from experiment.config import ModelSpec
from experiment.prompts import Prompt

# Anything that would route a CLI to an API key (and bill it), or mark it as running inside another agent.
_STRIPPED_ENV = re.compile(
    r"^(ANTHROPIC_|OPENAI_|CLAUDE_CODE_USE_|CLAUDECODE$|CLAUDE_CODE_ENTRYPOINT$|CLAUDE_CODE_SSE_PORT$|"
    r"CODEX_(API_KEY|AUTH_TOKEN|THREAD_ID|PARENT_THREAD_ID)$)"
)
_AUTH_HINTS = ("not logged in", "/login", "codex login", "invalid api key", "unauthorized", "401")
_MODEL_HINTS = ("model_not_found", "does not exist", "unknown model", "invalid model", "not supported")
_LIMIT_HINTS = ("usage limit", "session limit", "rate limit", "limit reached", "hit your", "quota", "429", "too many requests")


@dataclass
class Completion:
    text: str
    usage: dict  # input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens (None when not reported)
    served_model: str | None
    stop_reason: str | None
    session_id: str | None  # the CLI's id for the session, which must be new for every call
    # Why the call does not count: the harness went wrong, not the model (another model, not one fresh
    # turn, CLI errors). collect retries it.
    harness_failures: list[str] = field(default_factory=list)
    # What the model did beyond answering, such as trying a tool. The call still counts and is scored.
    model_flags: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)  # the CLI's own output, minus the response text


class ClientError(RuntimeError):
    """A call that failed without an answer. The next collect retries it."""


class UsageLimitError(ClientError):
    """The subscription hit its usage limit. Stop this model and collect again later."""


class InterruptedCallError(ClientError):
    """The call was stopped because collect was interrupted (Ctrl-C)."""


class FatalClientError(ClientError):
    """Every call would fail the same way (not logged in, model unavailable). Stop this model."""


class Client(Protocol):
    spec: ModelSpec
    version: str  # the CLI's version string, saved with every attempt

    def complete(self, prompt: Prompt, timeout: int) -> Completion: ...


def classify_error(provider: str, message: str) -> ClientError:
    text = " ".join(message.split())[:600]
    low = text.lower()
    if any(hint in low for hint in _AUTH_HINTS):
        return FatalClientError(f"{provider}: not logged in: {text}")
    if any(hint in low for hint in _MODEL_HINTS):
        return FatalClientError(f"{provider}: model unavailable on this plan: {text}")
    if any(hint in low for hint in _LIMIT_HINTS):
        return UsageLimitError(f"{provider}: usage limit reached, collect again later: {text}")
    return ClientError(f"{provider}: {text}")


def environment(**extra: str) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not _STRIPPED_ENV.match(key)}
    env.update(extra)
    return env


# Every CLI call still running, so an interrupted collect can stop them (each runs in its own process group).
_running: set[subprocess.Popen] = set()
_running_lock = threading.Lock()
_stopping = threading.Event()  # set once stop_all has killed the running calls


def run_cli(provider: str, cmd: list[str], stdin: str, cwd: str, env: dict[str, str], timeout: int) -> tuple[int, str, str]:
    """(exit code, stdout, stderr). On timeout the CLI and everything it started are killed."""
    try:
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, cwd=cwd, env=env, start_new_session=True)
    except OSError as error:
        raise FatalClientError(f"{provider}: could not start {cmd[0]}: {error}") from None
    with _running_lock:
        _running.add(process)
    try:
        stdout, stderr = process.communicate(stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill(process)
        process.communicate()
        raise ClientError(f"{provider}: no response after {timeout}s") from None
    finally:
        with _running_lock:
            _running.discard(process)
    if process.returncode < 0:
        if _stopping.is_set():
            raise InterruptedCallError(f"{provider}: stopped when collect was interrupted")
        raise ClientError(f"{provider}: killed by signal {-process.returncode}")
    return process.returncode, stdout, stderr


def stop_all() -> None:
    """Kill every CLI call still running (on Ctrl-C)."""
    _stopping.set()
    with _running_lock:
        processes = list(_running)
    for process in processes:
        _kill(process)


def _kill(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def cli_version(binary: str) -> str:
    return subprocess.run([binary, "--version"], capture_output=True, text=True).stdout.strip()
