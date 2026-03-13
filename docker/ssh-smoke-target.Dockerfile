FROM debian:bookworm-slim

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        netcat-openbsd \
        openssh-server \
        passwd \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /run/sshd /var/run/sshd

COPY docker/sshd_smoke_config /etc/ssh/sshd_config_smoke
COPY docker/start-ssh-smoke.sh /usr/local/bin/start-ssh-smoke.sh

RUN chmod 0755 /usr/local/bin/start-ssh-smoke.sh

EXPOSE 2222

CMD ["/usr/local/bin/start-ssh-smoke.sh"]
