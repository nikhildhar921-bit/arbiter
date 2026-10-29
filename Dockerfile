# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# uv, pinned. psycopg[binary] needs no build deps, so the image stays slim.
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /uvx /bin/

WORKDIR /app

# Dependencies first, so a code change does not re-resolve the whole lock file.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Then the project itself.
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY static/ ./static/
COPY sample-documents/ ./sample-documents/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# NOTE: the root project is installed editable, which is what makes
# BASE_DIR (= __file__/../../..) resolve to /app so static/ is found.
# If you ever switch to a non-editable install this breaks — see README note.

RUN useradd --create-home --uid 10001 arbiter && chown -R arbiter:arbiter /app
USER arbiter

EXPOSE 8000

# Migrations are NOT run here on purpose — see compose, they run as their own step.
CMD ["uvicorn", "arbiter:app", "--host", "0.0.0.0", "--port", "8000"]
