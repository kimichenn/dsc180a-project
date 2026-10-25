"""Model clients over the logged-in CLIs, so calls bill a subscription instead of an API key.

- claude-code: `claude -p` (Claude Code) on the Claude Pro/Max login.
- codex: `codex exec` (Codex CLI) on the ChatGPT login.
"""

from __future__ import annotations

from experiment.clients.base import Client, ClientError, Completion, FatalClientError, InterruptedCallError, UsageLimitError, stop_all
from experiment.config import ModelSpec


def make_client(spec: ModelSpec) -> Client:
    """A client for one model; raises FatalClientError when its CLI or login is missing."""
    if spec.provider == "claude-code":
        from experiment.clients.claude_code import ClaudeCodeClient

        return ClaudeCodeClient(spec)
    from experiment.clients.codex import CodexClient

    return CodexClient(spec)


__all__ = ["Client", "ClientError", "Completion", "FatalClientError", "InterruptedCallError", "UsageLimitError", "make_client", "stop_all"]
