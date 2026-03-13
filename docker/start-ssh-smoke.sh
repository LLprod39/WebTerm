#!/bin/sh
set -eu

SMOKE_SSH_USERNAME="${SMOKE_SSH_USERNAME:-smoke}"
SMOKE_SSH_PASSWORD="${SMOKE_SSH_PASSWORD:-smoke-password}"

if ! id "${SMOKE_SSH_USERNAME}" >/dev/null 2>&1; then
    useradd -m -s /bin/bash "${SMOKE_SSH_USERNAME}"
fi

echo "${SMOKE_SSH_USERNAME}:${SMOKE_SSH_PASSWORD}" | chpasswd

mkdir -p /run/sshd /var/run/sshd
ssh-keygen -A

exec /usr/sbin/sshd -D -e -f /etc/ssh/sshd_config_smoke
