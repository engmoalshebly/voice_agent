# syntax=docker/dockerfile:1
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
COPY --chmod=a+rX src ./src
RUN pip install . && useradd --create-home --uid 10001 voiceagent
COPY --from=web --chmod=a+rX /web/dist ./web/dist
ENV WEB_STATIC_DIR=/app/web/dist WEB_HOST=0.0.0.0
USER voiceagent
# Same image, two roles: `voice-web` (UI + tokens) or `voice-agent start` (worker).
CMD ["voice-web"]
