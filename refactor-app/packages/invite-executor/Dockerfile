FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    INVITE_EXECUTOR_HOST=0.0.0.0 \
    INVITE_EXECUTOR_PORT=8080

WORKDIR /build/refactor-app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libnss3 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libgbm1 \
        libgtk-3-0 \
        libasound2 \
        libxshmfence1 \
        libpangocairo-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Build with refactor-app as the Docker context. The executor imports the existing
# OpenAIChatGPTClient so invitation headers and payloads cannot drift.
COPY . /build/refactor-app

RUN pip install --no-cache-dir \
      "fastapi>=0.115,<1.0" \
      "uvicorn[standard]>=0.30,<1.0" \
      "pydantic-settings>=2.0,<3.0" \
      "httpx>=0.27,<1.0" \
      "requests>=2.32,<3.0" \
      "sqlalchemy>=2.0,<3.0" \
      "curl-cffi>=0.15,<1.0" \
      "camoufox[geoip]>=0.4,<1.0" \
    && pip install --no-cache-dir --no-deps /build/refactor-app \
    && pip install --no-cache-dir --no-deps /build/refactor-app/packages/invite-executor

RUN useradd --create-home --uid 10001 invite-executor \
    && mkdir -p /data/cache \
    && chown invite-executor:invite-executor /data
USER invite-executor
ENV HOME=/home/invite-executor \
    XDG_CACHE_HOME=/data/cache
# Camoufox downloads its browser binary lazily. Keeping the cache under /data
# avoids a large GitHub download during image build and preserves it across pod restarts.
WORKDIR /app

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)"

CMD ["invite-executor"]
