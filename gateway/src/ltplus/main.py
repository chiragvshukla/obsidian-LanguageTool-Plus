"""FastAPI application entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from openai import AsyncOpenAI

from ltplus import __version__
from ltplus.api import router
from ltplus.config import Settings, get_settings
from ltplus.lexicon import load_lexicon, validate_modes
from ltplus.modes import ModeConfigError, load_modes
from ltplus.rewrite import RewriteCache, load_prompts
from ltplus.rewrite import router as rewrite_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Mode configuration is validated before serving."""
    settings = settings or get_settings()

    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    modes = load_modes(settings.modes_dir)
    if settings.default_mode not in modes:
        raise ModeConfigError(f"default mode '{settings.default_mode}' is not defined")

    lexicon = load_lexicon(settings.rules_dir / "lexicon.yaml")
    validate_modes(lexicon, set(modes))
    prompts = load_prompts(settings.prompts_dir, modes)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with httpx.AsyncClient(
            base_url=settings.lt_url.rstrip("/"),
            timeout=settings.lt_timeout_seconds,
        ) as client:
            app.state.lt = client
            app.state.llm = AsyncOpenAI(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                timeout=settings.llm_timeout_seconds,
                max_retries=0,
            )
            try:
                yield
            finally:
                await app.state.llm.close()

    app = FastAPI(
        title="LanguageToolPlus",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.modes = modes
    app.state.lexicon = lexicon
    app.state.prompts = prompts
    app.state.rewrite_cache = RewriteCache(settings.llm_cache_size)
    app.include_router(router)
    app.include_router(rewrite_router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """Liveness probe. Does not call downstream services."""
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
