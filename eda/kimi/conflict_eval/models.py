"""One client per provider behind a common generate(prompt) -> Completion interface.

Every call is a fresh, stateless request with no tools, so there is no browsing,
retrieval, or memory. Settings come from config/models.toml and stay fixed for a study.
"""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

from conflict_eval.prompts import Prompt

API_KEY_ENV = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "google": "GEMINI_API_KEY"}
SDK_RETRIES = 5


@dataclass(frozen=True)
class ModelConfig:
    name: str  # short alias used in results, e.g. "gpt"
    provider: str  # openai | anthropic | google
    model: str  # exact API identifier
    reasoning: str | None = None  # provider-specific effort / thinking level
    temperature: float | None = None  # None = provider default
    max_output_tokens: int = 16000

    def record(self) -> dict:
        return {
            "provider": self.provider,
            "model_id": self.model,
            "reasoning": self.reasoning,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
        }


@dataclass
class Completion:
    text: str
    finish_reason: str | None = None
    model_version: str | None = None  # what the API reports actually serving
    usage: dict = field(default_factory=dict)


class ModelClient(Protocol):
    config: ModelConfig

    def generate(self, prompt: Prompt) -> Completion: ...


def load_model_configs(path: Path) -> dict[str, ModelConfig]:
    with open(path, "rb") as f:
        table = tomllib.load(f)
    configs = {name: ModelConfig(name=name, **settings) for name, settings in table.items()}
    for config in configs.values():
        if config.provider not in API_KEY_ENV:
            raise ValueError(f"{config.name}: unknown provider {config.provider!r}")
    return configs


def make_client(config: ModelConfig) -> ModelClient:
    clients = {"openai": OpenAIClient, "anthropic": AnthropicClient, "google": GeminiClient}
    return clients[config.provider](config)


def is_fatal(error: Exception) -> bool:
    """True for request errors that retrying cannot fix (bad key, unknown model, invalid parameter)."""
    status = getattr(error, "status_code", None) or getattr(error, "code", None)
    return isinstance(status, int) and 400 <= status < 500 and status not in (408, 409, 429)


def _as_dict(usage) -> dict:
    if usage is None:
        return {}
    return usage.model_dump(exclude_none=True) if hasattr(usage, "model_dump") else dict(usage)


class OpenAIClient:
    def __init__(self, config: ModelConfig):
        from openai import OpenAI

        self.config = config
        self._client = OpenAI(max_retries=SDK_RETRIES)

    def generate(self, prompt: Prompt) -> Completion:
        c = self.config
        request = dict(
            model=c.model,
            instructions=prompt.system,
            input=prompt.messages,
            max_output_tokens=c.max_output_tokens,
            store=False,  # nothing persists between trials
        )
        if c.reasoning:
            request["reasoning"] = {"effort": c.reasoning}
        if c.temperature is not None:
            request["temperature"] = c.temperature
        response = self._client.responses.create(**request)
        finish = response.status
        if response.incomplete_details is not None:
            finish = f"{finish}:{response.incomplete_details.reason}"
        return Completion(response.output_text, finish, response.model, _as_dict(response.usage))


class AnthropicClient:
    def __init__(self, config: ModelConfig):
        import anthropic

        self.config = config
        self._client = anthropic.Anthropic(max_retries=SDK_RETRIES)

    def generate(self, prompt: Prompt) -> Completion:
        # Refusal fallbacks are deliberately left off: a fallback would answer with a
        # different model. A refusal is recorded as finish_reason="refusal" instead.
        c = self.config
        request = dict(model=c.model, max_tokens=c.max_output_tokens, system=prompt.system, messages=prompt.messages)
        if c.reasoning:
            request["output_config"] = {"effort": c.reasoning}
        if c.temperature is not None:
            request["extra_body"] = {"temperature": c.temperature}  # rejected by Claude Opus 5.5
        response = self._client.messages.create(**request)
        text = "".join(block.text for block in response.content if block.type == "text")
        return Completion(text, response.stop_reason, response.model, _as_dict(response.usage))


class GeminiClient:
    def __init__(self, config: ModelConfig):
        from google import genai
        from google.genai import types

        self.config = config
        self._types = types
        retry = types.HttpRetryOptions(attempts=SDK_RETRIES)
        self._client = genai.Client(http_options=types.HttpOptions(retry_options=retry))

    def generate(self, prompt: Prompt) -> Completion:
        types, c = self._types, self.config
        contents = [
            types.Content(role="user" if m["role"] == "user" else "model", parts=[types.Part(text=m["content"])])
            for m in prompt.messages
        ]
        config = types.GenerateContentConfig(
            system_instruction=prompt.system,
            max_output_tokens=c.max_output_tokens,
            temperature=c.temperature,
            thinking_config=types.ThinkingConfig(thinking_level=c.reasoning) if c.reasoning else None,
        )
        response = self._client.models.generate_content(model=c.model, contents=contents, config=config)
        finish = None
        if response.candidates:
            reason = response.candidates[0].finish_reason
            finish = getattr(reason, "name", None) or (str(reason) if reason else None)
        return Completion(response.text or "", finish, response.model_version, _as_dict(response.usage_metadata))


def config_table(configs: dict[str, ModelConfig]) -> dict[str, dict]:
    return {name: asdict(config) for name, config in configs.items()}
