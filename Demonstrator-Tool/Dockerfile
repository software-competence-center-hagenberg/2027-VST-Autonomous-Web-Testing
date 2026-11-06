# ---------------------------------------------------------------------------
# Stage 1: build the static frontend (Node is only needed here)
# ---------------------------------------------------------------------------
FROM node:22-bookworm-slim AS frontend-build

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN VITE_BROWSER_STREAMING=true npm run build

# ---------------------------------------------------------------------------
# Stage 2: runtime — FastAPI backend serving the API and the built frontend
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.8.4 /uv /uvx /bin/

ENV DEBIAN_FRONTEND=noninteractive \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    UV_PROJECT_ENVIRONMENT=/app/backend/.venv \
    UV_NO_SYNC=1 \
    UV_NO_CACHE=1 \
    DEMO_CONTAINER=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      bash \
      ca-certificates \
      curl \
      tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash app \
    && mkdir -p /app /ms-playwright \
    && chown app:app /app /ms-playwright

# Everything below is created as the unprivileged user, so no recursive chown
# (which would duplicate the whole tree in an extra image layer) is needed.
USER app
WORKDIR /app

COPY --chown=app:app backend/ /app/backend/
COPY --chown=app:app backend/tasks/ /app/task-examples/
COPY --chown=app:app --chmod=755 demo-models.json start-demo.sh /app/

WORKDIR /app/backend
RUN sed -i 's/\r$//' /app/start-demo.sh \
    && uv sync --frozen --no-dev \
    && /app/backend/.venv/bin/playwright install chromium \
    && mkdir -p /app/backend/tasks /app/backend/logs

# System libraries for Chromium need root; this layer only adds apt packages.
USER root
RUN /app/backend/.venv/bin/playwright install-deps chromium \
    && rm -rf /var/lib/apt/lists/*

USER app
COPY --from=frontend-build --chown=app:app /frontend/dist /app/frontend/dist

WORKDIR /app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD curl --fail --silent http://127.0.0.1:8000/api/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["./start-demo.sh", "--task-retention-minutes", "60"]
