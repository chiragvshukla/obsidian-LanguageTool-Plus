"""Runtime configuration, read from environment variables only."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Source checkout: gateway/src/ltplus/config.py -> repository root.
_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Gateway settings. Every field has a safe local default."""

    model_config = SettingsConfigDict(
        env_file=(_ROOT / ".env",),
        extra="ignore",
    )

    # LanguageTool
    lt_url: str = "http://127.0.0.1:8010"
    lt_timeout_seconds: float = 10.0

    # OpenAI-compatible LLM (used from Phase 3)
    llm_base_url: str = "http://127.0.0.1:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "gemma4:e4b-it-q4_K_M"
    llm_timeout_seconds: float = 60.0
    llm_max_tokens: int = 4096
    llm_context_chars: int = 12000
    llm_cache_size: int = 128

    # Gateway
    log_level: str = "INFO"
    default_mode: str = "neutral"
    default_language: str = "de-DE"

    # Paths resolve from the repository root. Relative env values keep the
    # documented meaning: relative to gateway/, the working directory.
    modes_dir: Path = _ROOT / "modes"
    rules_dir: Path = _ROOT / "rules"
    prompts_dir: Path = _ROOT / "prompts"
    dictionary_dir: Path = _ROOT / "data" / "dictionary"

    @field_validator("modes_dir", "rules_dir", "prompts_dir", "dictionary_dir", mode="after")
    @classmethod
    def _resolve_path(cls, value: Path) -> Path:
        if value.is_absolute():
            return value
        return (_ROOT / "gateway" / value).resolve()


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
