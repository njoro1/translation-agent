"""Configuration and OpenAI client setup.

Reads credentials/settings from environment (or a local .env file) so the
CLI never has to hardcode secrets.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from dotenv import load_dotenv
from openai import OpenAI

# Load .env if present (no-op if missing).
load_dotenv()

ENV_API_KEY = "OPENAI_API_KEY"
ENV_BASE_URL = "OPENAI_BASE_URL"
ENV_MODEL = "OPENAI_MODEL"

# Local endpoints (e.g. a llama-cpp-python server) don't require a real key.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _is_local(base_url: str) -> bool:
    """True if the base URL points at this machine."""
    host = urlparse(base_url).hostname or ""
    return host in _LOCAL_HOSTS or host.endswith(".localhost")


def _api_key_or_local(api_key: str, base_url: str | None) -> str:
    """Require a key for remote endpoints; allow a placeholder locally."""
    if api_key:
        return api_key
    if base_url and _is_local(base_url):
        return "sk-local"
    raise RuntimeError(
        f"Missing {ENV_API_KEY}. Set it in your environment or a .env file "
        f"(see .env.example). Local servers (localhost) accept any placeholder."
    )


@dataclass
class Settings:
    api_key: str
    base_url: str | None
    model: str


def load_settings(override_model: str | None = None) -> Settings:
    """Load settings from the environment, validating the essentials.

    Raises a clear error if the API key or model is missing so the user is
    told exactly what to set rather than getting an opaque SDK failure.
    """
    api_key = os.environ.get(ENV_API_KEY, "").strip()
    base_url = os.environ.get(ENV_BASE_URL, "").strip() or None
    if not api_key:
        api_key = _api_key_or_local(api_key, base_url)

    model = (override_model or os.environ.get(ENV_MODEL, "")).strip()
    if not model:
        raise RuntimeError(
            f"Missing {ENV_MODEL}. Pass --model or set it in your environment / .env."
        )

    return Settings(api_key=api_key, base_url=base_url, model=model)


def make_client(settings: Settings) -> OpenAI:
    """Construct an OpenAI-compatible client from settings."""
    kwargs: dict = {"api_key": settings.api_key}
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
        # OpenRouter's documented attribution headers (optional but recommended).
        if "openrouter" in settings.base_url:
            kwargs["default_headers"] = {
                "HTTP-Referer": "https://github.com/translation-agent",
                "X-Title": "YouTube Subtitle Translator",
            }
    return OpenAI(**kwargs)
