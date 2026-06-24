FROM node:22-slim AS frontend-build
WORKDIR /src
COPY . .
RUN cd frontend && npm install && npm run build

FROM python:3.12-slim
LABEL "language"="python"
LABEL "framework"="fastapi"
WORKDIR /src
COPY . .
COPY --from=frontend-build /src/frontend/dist /src/frontend/dist
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
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
RUN pip install --no-cache-dir .
RUN python -m camoufox fetch
RUN chmod +x /src/scripts/start-zeabur.sh
EXPOSE 8080
CMD ["/src/scripts/start-zeabur.sh"]
