"""The prompt every model client takes: one system text and a list of chat messages."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Prompt:
    system: str
    messages: list[dict[str, str]]
