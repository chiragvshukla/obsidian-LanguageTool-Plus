"""Runtime configuration, read from environment variables only."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Gateway settings. Every field has a safe local default."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        extra="ignore",
    )

    # LanguageTool
    lt_url: str = "http://127.0.0.1:8010"
    lt_timeout_seconds: float = 10.0

    # OpenAI-compatible LLM
    llm_base_url: str = "http://127.0.0.1:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "gemma4:e4b-it-q4_K_M"
    llm_timeout_seconds: float = 30.0
    llm_max_tokens: int = 1024
    llm_context_chars: int = 12000

    # Gateway
    gateway_host: str = "127.0.0.1"
    gateway_port: int = 8077
    log_level: str = "INFO"
    default_mode: str = "neutral"
    default_language: str = "de-DE"
    cache_size: int = 256

    # Paths, relative to the process working directory
    modes_dir: Path = Path("../modes")
    rules_dir: Path = Path("../rules")
    prompts_dir: Path = Path("../prompts")
    dictionary_dir: Path = Path("../data/dictionary")


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
