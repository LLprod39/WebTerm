FROM python:3.11-slim

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
    PYTHONUNBUFFERED=1

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    docker.io \
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
RUN chmod +x docker/render-backend-start.sh

EXPOSE 9000
CMD ["./docker/render-backend-start.sh"]
