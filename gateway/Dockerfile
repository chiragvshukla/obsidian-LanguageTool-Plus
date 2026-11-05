# syntax=docker/dockerfile:1
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY gateway/pyproject.toml gateway/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY gateway/src ./src
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8077

CMD ["uvicorn", "ltplus.main:app", "--host", "0.0.0.0", "--port", "8077"]