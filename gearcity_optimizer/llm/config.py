"""Optional LLM backend configuration."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Literal

LLMBackend = Literal["none", "ollama", "openai_compatible"]

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3:latest"
DEFAULT_OPENAI_COMPAT_BASE_URL = "http://localhost:1234/v1"
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_TEMPERATURE = 0.0

LLM_NOT_CONFIGURED_MESSAGE = (
    "LLM-assisted mode is not configured. Install/configure Ollama or switch to Deterministic only."
)


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for optional LLM strategy assistance."""

    enabled: bool = False
    backend: LLMBackend = "none"
    model: str = DEFAULT_OLLAMA_MODEL
    base_url: str = DEFAULT_OLLAMA_BASE_URL
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    temperature: float = DEFAULT_TEMPERATURE
    api_key: str | None = None


def load_llm_config_from_env() -> LLMConfig:
    """Load LLM config from environment variables."""
    enabled_raw = os.getenv("GEARCITY_LLM_ENABLED", "").strip().lower()
    enabled = enabled_raw in {"1", "true", "yes", "on"}
    backend_raw = os.getenv("GEARCITY_LLM_BACKEND", "none").strip().lower()
    backend: LLMBackend = "none"
    if backend_raw in {"ollama", "openai_compatible"}:
        backend = backend_raw  # type: ignore[assignment]
    elif enabled and backend_raw not in {"", "none"}:
        backend = "ollama"

    if enabled and backend == "none":
        backend = "ollama"

    return LLMConfig(
        enabled=enabled,
        backend=backend,
        model=os.getenv("GEARCITY_LLM_MODEL", DEFAULT_OLLAMA_MODEL).strip() or DEFAULT_OLLAMA_MODEL,
        base_url=normalize_llm_base_url(
            os.getenv("GEARCITY_LLM_BASE_URL", DEFAULT_OLLAMA_BASE_URL),
            backend=backend,
        ),
        timeout=float(os.getenv("GEARCITY_LLM_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS))),
        temperature=float(os.getenv("GEARCITY_LLM_TEMPERATURE", str(DEFAULT_TEMPERATURE))),
        api_key=os.getenv("GEARCITY_LLM_API_KEY"),
    )


def normalize_llm_base_url(raw: str, *, backend: LLMBackend) -> str:
    """Normalize user-entered base URLs and apply backend defaults."""
    if backend == "ollama" and not raw.strip():
        return DEFAULT_OLLAMA_BASE_URL
    if backend == "openai_compatible" and not raw.strip():
        return DEFAULT_OPENAI_COMPAT_BASE_URL

    value = raw.strip().replace("\\", "/")
    value = re.sub(r"^(https?):/+", r"\1://", value)
    if not value.startswith(("http://", "https://")):
        if backend == "ollama":
            return DEFAULT_OLLAMA_BASE_URL
        raise ValueError(
            f"LLM base URL must start with http:// or https://, got {raw!r}."
        )
    return value.rstrip("/")


def resolve_llm_config(
    *,
    enabled: bool,
    backend: LLMBackend,
    model: str,
    base_url: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    temperature: float = DEFAULT_TEMPERATURE,
    api_key: str | None = None,
) -> LLMConfig:
    """Build a normalized LLM config with safe defaults for each backend."""
    normalized_backend: LLMBackend = backend if enabled else "none"
    normalized_model = model.strip() or DEFAULT_OLLAMA_MODEL
    normalized_url = normalize_llm_base_url(base_url, backend=backend)
    return LLMConfig(
        enabled=enabled,
        backend=normalized_backend,
        model=normalized_model,
        base_url=normalized_url,
        timeout=timeout,
        temperature=temperature,
        api_key=api_key,
    )


def is_llm_configured(config: LLMConfig | None = None) -> bool:
    """Return True when an LLM backend is enabled and selected."""
    cfg = config if config is not None else load_llm_config_from_env()
    return cfg.enabled and cfg.backend != "none"
