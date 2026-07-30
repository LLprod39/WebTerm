FROM node:22.23.1-bookworm-slim

ARG WEBTERM_VERSION=0.2.1
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
    CHOKIDAR_USEPOLLING=true \
    WATCHPACK_POLLING=true \
    WEBTERM_VERSION=${WEBTERM_VERSION}

LABEL org.opencontainers.image.title="WebTerm" \
      org.opencontainers.image.version=${WEBTERM_VERSION} \
      org.opencontainers.image.source="https://github.com/LLprod39/WebTerm"

WORKDIR /workspace/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

EXPOSE 8080

CMD ["npx", "vite", "preview", "--host", "0.0.0.0", "--port", "8080"]
