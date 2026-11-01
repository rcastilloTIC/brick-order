# VALBRICK release candidate - Python 3.11, non-root production runtime.
FROM python:3.11-slim AS builder
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /build
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt && python -m pip check

FROM python:3.11-slim
RUN groupadd --system --gid 10001 valbrick \
    && useradd --system --uid 10001 --gid valbrick --no-create-home --home-dir /tmp valbrick
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY . .
USER valbrick
EXPOSE 5001
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
CMD ["gunicorn", "--workers", "1", "-b", "0.0.0.0:5001", "run:app"]
