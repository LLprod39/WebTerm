FROM node:22-bookworm-slim

ARG CODEX_NPM_PACKAGE="@openai/codex@0.139.0"
ARG GEMINI_NPM_PACKAGE="@google/gemini-cli@0.46.0"

ENV DEBIAN_FRONTEND=noninteractive \
    npm_config_update_notifier=false \
    npm_config_fund=false \
    npm_config_audit=false

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    build-essential \
    ca-certificates \
    chromium \
    git \
    openssh-client \
    python3 \
    python3-pip \
    python3-venv \
    ripgrep \
    && rm -rf /var/lib/apt/lists/*

RUN corepack enable || true \
    && npm install -g "${CODEX_NPM_PACKAGE}" "${GEMINI_NPM_PACKAGE}" \
    && npm cache clean --force

RUN mkdir -p /workspace /mars-run /mars-interview /codex-home \
    && chown -R node:node /workspace /mars-run /mars-interview /codex-home

USER node
WORKDIR /workspace

ENV HOME=/home/node \
    CODEX_HOME=/codex-home \
    PLAYWRIGHT_BROWSERS_PATH=/usr/bin
