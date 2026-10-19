FROM python:3.11-alpine

LABEL org.opencontainers.image.version="1.0.0"

WORKDIR /app

# Build context is the repository root (see docker-compose.yml)
COPY bridge/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared ./shared
COPY bridge/app.py .

EXPOSE 13714

CMD ["gunicorn", "--bind", "0.0.0.0:13714", "--workers", "2", "--threads", "4", "app:app"]
