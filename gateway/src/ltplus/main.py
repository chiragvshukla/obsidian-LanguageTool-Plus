"""FastAPI application entry point.

The scaffold exposes only a health check. LanguageTool-compatible endpoints are
added in Phase 1; see docs/PLAN.md.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from ltplus import __version__
from ltplus.config import get_settings

settings = get_settings()

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(
    title="LanguageToolPlus",
    version=__version__,
    docs_url=None,
    redoc_url=None,
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe. Does not call downstream services."""
    return {"status": "ok", "version": __version__}
