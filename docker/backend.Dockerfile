ARG DOCKER_CLI_IMAGE=docker:29.1.2-cli
FROM ${DOCKER_CLI_IMAGE} AS docker-cli

FROM python:3.11.15-slim-bookworm

ARG WEBTERM_VERSION=0.1.0
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
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WEBTERM_VERSION=${WEBTERM_VERSION}

LABEL org.opencontainers.image.title="WebTerm" \
      org.opencontainers.image.version=${WEBTERM_VERSION} \
      org.opencontainers.image.source="https://github.com/LLprod39/WebTerm"

WORKDIR /workspace

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
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

COPY . .
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
RUN chmod +x docker/render-backend-start.sh

EXPOSE 9000
CMD ["./docker/render-backend-start.sh"]
