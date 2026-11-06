"""FastAPI application entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from ltplus import __version__
from ltplus.api import router
from ltplus.config import Settings, get_settings
from ltplus.lexicon import load_lexicon, validate_modes
from ltplus.modes import ModeConfigError, load_modes


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

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with httpx.AsyncClient(
            base_url=settings.lt_url.rstrip("/"),
            timeout=settings.lt_timeout_seconds,
        ) as client:
            app.state.lt = client
            yield

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
    app.include_router(router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """Liveness probe. Does not call downstream services."""
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
