"""Calling a model client: retries on top of the SDKs' own, and the error that stops a whole run."""

from __future__ import annotations

import subprocess
import time

from harness.models import ModelClient, is_fatal

ATTEMPTS = 3  # on top of the SDKs' own retries
BACKOFF_S = 10


class FatalModelError(RuntimeError):
    """A request error that will repeat on every trial, such as a bad key or unknown model."""


def generate_with_retries(client: ModelClient, prompt):
    for attempt in range(ATTEMPTS):
        try:
            return client.generate(prompt)
        except Exception as error:
            if is_fatal(error):
                raise FatalModelError(f"{client.config.name}: {type(error).__name__}: {error}") from error
            if attempt == ATTEMPTS - 1:
                raise
            time.sleep(BACKOFF_S * 2**attempt)


def git_commit() -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
