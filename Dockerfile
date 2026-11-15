# syntax=docker/dockerfile:1

# --- build the frontend ---------------------------------------------------------
FROM node:24-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- runtime ----------------------------------------------------------------------
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CLEA_DB=/data/clea.db \
    CLEA_HOST=0.0.0.0 \
    CLEA_PORT=6942 \
    CLEA_STATIC_DIR=/app/static
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY clea/ clea/
COPY sites.toml ./
COPY --from=frontend /app/frontend/dist /app/static
RUN useradd --system --uid 10001 --no-create-home clea && mkdir -p /data && chown clea /data
USER clea
VOLUME ["/data"]
EXPOSE 6942
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:6942/api/health', timeout=4)"
CMD ["python", "-m", "clea", "serve"]
