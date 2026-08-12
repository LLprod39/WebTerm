FROM python:3.11.15-slim-bookworm AS builder

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
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    libldap2-dev \
    libsasl2-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# requirements.lock is compiled from requirements-mini.txt (pinned + hashed).
# Regenerate after changing requirements-mini.txt:
#   uv pip compile requirements-mini.txt -o requirements.lock \
#     --python-version 3.11 --python-platform linux --generate-hashes
COPY requirements.lock ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --require-hashes -r requirements.lock \
    && /opt/venv/bin/pip uninstall --yes pip setuptools wheel


FROM python:3.11.15-slim-bookworm AS runtime

ARG WEBTERM_VERSION=0.2.3
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
    PATH=/opt/venv/bin:${PATH} \
    HOME=/home/webterm \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WEBTERM_VERSION=${WEBTERM_VERSION}

LABEL org.opencontainers.image.title="WebTerm" \
      org.opencontainers.image.version=${WEBTERM_VERSION} \
      org.opencontainers.image.source="https://github.com/LLprod39/WebTerm"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libldap-2.5-0 \
    libsasl2-2 \
    libssl3 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 webterm \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin webterm \
    && printf '%s\n' 'export PATH="/opt/venv/bin:$PATH"' > /etc/profile.d/webterm-venv.sh

WORKDIR /workspace

COPY --from=builder /opt/venv /opt/venv
COPY --from=docker:29.1.2-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --chown=10001:10001 . .

RUN chmod 0755 docker/render-backend-start.sh \
    && install -d -o 10001 -g 10001 -m 0755 \
        /workspace/media \
        /workspace/media/uploads \
        /workspace/staticfiles \
    && install -d -o 10001 -g 10001 -m 0750 \
        /home/webterm \
        /workspace/agent_projects \
        /workspace/config_runtime \
        /workspace/data/ssh_keys \
        /workspace/logs \
        /workspace/private/playbook_bundles \
        /playbook-runtime \
    && DJANGO_SETTINGS_MODULE=web_ui.settings.test python manage.py collectstatic --noinput

USER 10001:10001

EXPOSE 9000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; req=urllib.request.Request('http://127.0.0.1:9000/api/ready/?scope=core', headers={'X-Forwarded-Proto': 'https', 'Host': '127.0.0.1'}); urllib.request.urlopen(req, timeout=4).read()"
CMD ["./docker/render-backend-start.sh"]
