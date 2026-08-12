FROM python:3.11.15-slim-bookworm AS runtime-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/ai-cli \
    PATH=/opt/venv/bin:/usr/local/bin:${PATH}

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 ai-cli \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin ai-cli

WORKDIR /app
RUN python -m venv --without-pip /opt/venv

COPY --chown=10001:10001 app/ai_runtime /app/app/ai_runtime
COPY --chown=10001:10001 ai_cli_runner_manager /app/ai_cli_runner_manager
RUN install -d -o 10001 -g 10001 /credentials /credentials/codex /credentials/grok /workspace

USER 10001:10001
WORKDIR /workspace
ENTRYPOINT ["python", "-m", "ai_cli_runner_manager.provider_runtime"]

# Codex and Grok are deliberately separate release artifacts. The runner
# manager selects one immutable digest from the requested provider target, so a
# compromised or stale provider image cannot impersonate the other provider.
FROM runtime-base AS codex
USER root
COPY ai_cli_runner_manager/provider-requirements.lock /app/provider-requirements.lock
RUN /opt/venv/bin/python -m ensurepip \
    && /opt/venv/bin/pip install --no-cache-dir --require-hashes --requirement /app/provider-requirements.lock \
    && /opt/venv/bin/pip uninstall --yes pip setuptools wheel
USER 10001:10001

FROM runtime-base AS grok
ARG GROK_BUILD_URL
ARG GROK_BUILD_SHA256
USER root
# Grok Build is supplied as a reviewed official artifact. Empty inputs,
# non-HTTPS URLs, malformed checksums, download failures and checksum mismatches
# all fail the image build before the binary is installed.
RUN test -n "${GROK_BUILD_URL}" \
    && test -n "${GROK_BUILD_SHA256}" \
    && case "${GROK_BUILD_URL}" in https://*) ;; *) exit 1 ;; esac \
    && echo "${GROK_BUILD_SHA256}" | grep -Eq '^[0-9a-f]{64}$' \
    && curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
        "${GROK_BUILD_URL}" -o /tmp/grok \
    && echo "${GROK_BUILD_SHA256}  /tmp/grok" | sha256sum --check --strict - \
    && install -o root -g root -m 0755 /tmp/grok /usr/local/bin/grok \
    && rm -f /tmp/grok
USER 10001:10001
