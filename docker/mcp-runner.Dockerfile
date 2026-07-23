# MCP Runner: one supervisor container that spawns and multiplexes stdio MCP
# servers for the backend (node for npx-based MCP, python for script-based MCP).
FROM node:22-bookworm-slim

ARG http_proxy
ARG https_proxy
ARG ftp_proxy
ARG no_proxy
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG FTP_PROXY
ARG NO_PROXY

ENV http_proxy=${http_proxy} \
    https_proxy=${https_proxy} \
    ftp_proxy=${ftp_proxy} \
    no_proxy=${no_proxy} \
    HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    FTP_PROXY=${FTP_PROXY} \
    NO_PROXY=${NO_PROXY} \
    DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    npm_config_update_notifier=false \
    npm_config_fund=false \
    npm_config_audit=false

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    git \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY mcp_runner/requirements.txt /app/mcp_runner/requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /app/mcp_runner/requirements.txt
ENV PATH="/opt/venv/bin:${PATH}"

COPY mcp_runner /app/mcp_runner

# Writable caches so npx/uvx reuse downloads across spawns instead of refetching.
ENV NPM_CONFIG_CACHE=/app/.cache/npm \
    UV_CACHE_DIR=/app/.cache/uv \
    XDG_CACHE_HOME=/app/.cache
RUN mkdir -p /app/.cache/npm /app/.cache/uv

EXPOSE 9000

HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9000/health', timeout=5).read()" || exit 1

CMD ["uvicorn", "mcp_runner.server:app", "--host", "0.0.0.0", "--port", "9000"]
