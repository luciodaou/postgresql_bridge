FROM python:3.11-alpine

LABEL org.opencontainers.image.version="1.0.0"

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH"

# Build context is the repository root (see docker-compose.yml)
COPY cron/pyproject.toml cron/uv.lock cron/README.md ./
RUN uv sync --frozen --no-install-project --no-dev

COPY shared ./shared
COPY cron/src ./src
RUN uv sync --frozen --no-dev

# Syncs and output are bind-mounted at runtime; the image itself stays read-only
CMD ["psql-cron"]
