# Local/pilot Cursor subscription runner using the official Cursor lab package.
# Production pin still goes through reviewed CURSOR_AGENT_URL single-artifact builds
# when available; the published lab artifact is a tarball with node + cursor-agent.
FROM python:3.11.15-slim-bookworm AS runtime-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/ai-cli \
    PYTHONPATH=/app \
    PATH=/opt/venv/bin:/usr/local/bin:/opt/cursor-agent:${PATH}

ARG CURSOR_AGENT_PACKAGE_URL=https://downloads.cursor.com/lab/2026.09.10-fd3934a/linux/x64/agent-cli-package.tar.gz
ARG CURSOR_AGENT_PACKAGE_SHA256=27997c8391ad853a5a732b1845db8ef82a8ba6afb0f7829cc739464f8966e96e

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl bash \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 ai-cli \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin ai-cli

WORKDIR /app
RUN python -m venv --without-pip /opt/venv

COPY --chown=10001:10001 app/ai_runtime /app/app/ai_runtime
COPY --chown=10001:10001 ai_cli_runner_manager /app/ai_cli_runner_manager
RUN install -d -o 10001 -g 10001 /credentials /credentials/codex /credentials/grok /credentials/cursor /workspace \
    /opt/cursor-agent /home/ai-cli/.cache

# Official Cursor agent package (node runtime + cursor-agent launcher).
RUN test -n "${CURSOR_AGENT_PACKAGE_URL}" \
    && test -n "${CURSOR_AGENT_PACKAGE_SHA256}" \
    && case "${CURSOR_AGENT_PACKAGE_URL}" in https://*) ;; *) exit 1 ;; esac \
    && echo "${CURSOR_AGENT_PACKAGE_SHA256}" | grep -Eq '^[0-9a-f]{64}$' \
    && curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
        "${CURSOR_AGENT_PACKAGE_URL}" -o /tmp/agent-cli-package.tar.gz \
    && echo "${CURSOR_AGENT_PACKAGE_SHA256}  /tmp/agent-cli-package.tar.gz" | sha256sum --check --strict - \
    && tar -xzf /tmp/agent-cli-package.tar.gz -C /opt/cursor-agent --strip-components=1 \
    && test -x /opt/cursor-agent/cursor-agent \
    && test -x /opt/cursor-agent/node \
    && ln -sf /opt/cursor-agent/cursor-agent /usr/local/bin/agent \
    && chmod -R a+rX /opt/cursor-agent \
    && rm -f /tmp/agent-cli-package.tar.gz \
    && agent --version || agent --help || true

USER 10001:10001
WORKDIR /workspace
ENTRYPOINT ["python", "-m", "ai_cli_runner_manager.provider_runtime"]
