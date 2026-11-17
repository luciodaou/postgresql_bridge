FROM python:3.11-alpine

LABEL org.opencontainers.image.version="1.0.0"

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    HOME=/tmp

# Build context is the repository root (see docker-compose.yml).
# No DB driver or bridge code: data comes only from postgres-bridge over HTTP.
COPY web/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY web/server.py ./
# Baked-in copy of the pages; docker-compose.yml also bind-mounts web/static so edits need no rebuild
COPY web/static ./static

EXPOSE 13715

CMD ["gunicorn", "--bind", "0.0.0.0:13715", "--workers", "2", "--threads", "4", "--worker-tmp-dir", "/tmp", "server:app"]
