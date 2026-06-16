from __future__ import annotations

import re

CAPABILITIES_COMMAND = """
printf 'hostname=%s\n' "$(hostname 2>/dev/null || true)"
printf 'current_user=%s\n' "$(id -un 2>/dev/null || whoami 2>/dev/null || true)"
if [ -r /etc/os-release ]; then
  . /etc/os-release 2>/dev/null
  printf 'os_name=%s\n' "${PRETTY_NAME:-${NAME:-unknown}}"
  printf 'os_id=%s\n' "${ID:-unknown}"
else
  printf 'os_name=\n'
  printf 'os_id=\n'
fi
printf 'kernel=%s\n' "$(uname -srmo 2>/dev/null || true)"
for cmd in systemctl journalctl docker ss ip apt apt-get dnf yum python3 bash sh; do
  if command -v "$cmd" >/dev/null 2>&1; then
    printf 'cmd_%s=1\n' "$cmd"
  else
    printf 'cmd_%s=0\n' "$cmd"
  fi
done
if [ -d /run/systemd/system ] || command -v systemctl >/dev/null 2>&1; then
  printf 'is_systemd=1\n'
else
  printf 'is_systemd=0\n'
fi
"""

OVERVIEW_COMMAND = """
printf 'hostname=%s\n' "$(hostname 2>/dev/null || true)"
printf 'current_user=%s\n' "$(id -un 2>/dev/null || whoami 2>/dev/null || true)"
printf 'home_path=%s\n' "${HOME:-}"
printf 'cwd=%s\n' "$(pwd 2>/dev/null || true)"
if [ -r /etc/os-release ]; then
  . /etc/os-release 2>/dev/null
  printf 'os_name=%s\n' "${PRETTY_NAME:-${NAME:-unknown}}"
else
  printf 'os_name=\n'
fi
printf 'kernel=%s\n' "$(uname -srmo 2>/dev/null || true)"
printf 'uptime_seconds=%s\n' "$(cut -d. -f1 /proc/uptime 2>/dev/null || true)"
printf 'loadavg=%s\n' "$(cut -d' ' -f1-3 /proc/loadavg 2>/dev/null || true)"
printf 'mem_line=%s\n' "$(free -m 2>/dev/null | awk '/^Mem:/ {print $2\",\"$3}')"
printf 'disk_line=%s\n' "$(df -kP / 2>/dev/null | awk 'NR==2 {print $2\",\"$3\",\"$5}')"
printf 'process_count=%s\n' "$(ps aux --no-headers 2>/dev/null | wc -l | tr -d ' ')"
"""

SETTINGS_COMMAND = """
printf '__GENERAL_HOSTNAME__\n'
hostname -f 2>/dev/null || hostname 2>/dev/null || true
printf '\n__GENERAL_TIMEZONE__\n'
timedatectl show --property=Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo unknown
printf '\n__GENERAL_KERNEL__\n'
uname -r 2>/dev/null || true
printf '\n__GENERAL_OS_RELEASE__\n'
cat /etc/os-release 2>/dev/null | head -5
printf '\n__GENERAL_UPTIME__\n'
uptime -p 2>/dev/null || uptime 2>/dev/null || true
printf '\n__GENERAL_ARCH__\n'
uname -m 2>/dev/null || true
printf '\n__GENERAL_CPU__\n'
printf '%s\n' "$(nproc 2>/dev/null | tr -d '\n') $(awk -F: '/model name/ {gsub(/^[ \t]+/, "", $2); print $2; exit}' /proc/cpuinfo 2>/dev/null)"
printf '\n__GENERAL_MEMORY__\n'
free -h 2>/dev/null | awk 'NR==2 {print $2}'
printf '\n__USERS_CURRENT__\n'
whoami 2>/dev/null || id -un 2>/dev/null || true
printf '\n__USERS_LIST__\n'
awk -F: '$3 >= 1000 && $3 < 65534 { print $1":"$3":"$6":"$7 }' /etc/passwd 2>/dev/null
printf '\n__USERS_LOGGED_IN__\n'
who 2>/dev/null || w -h 2>/dev/null || true
printf '\n__USERS_LAST_LOGINS__\n'
last -10 2>/dev/null | head -12
printf '\n__USERS_SUDO_GROUP__\n'
getent group sudo 2>/dev/null || getent group wheel 2>/dev/null || echo 'N/A'
printf '\n__CRONTAB_USER__\n'
crontab -l 2>/dev/null || echo 'No crontab for current user'
printf '\n__CRONTAB_SYSTEM__\n'
cat /etc/crontab 2>/dev/null || echo 'No /etc/crontab'
printf '\n__CRONTAB_DIRS__\n'
ls -la /etc/cron.d/ 2>/dev/null | tail -20 || echo 'No /etc/cron.d/'
printf '\n__CRONTAB_TIMERS__\n'
systemctl list-timers --no-pager 2>/dev/null | head -20 || echo 'systemctl unavailable'
printf '\n__ENVIRONMENT_VARS__\n'
env | sort | head -50
printf '\n__ENVIRONMENT_PATH__\n'
echo "${PATH:-}" | tr ':' '\n'
printf '\n__ENVIRONMENT_SHELL__\n'
echo "${SHELL:-}"
printf '\n__ENVIRONMENT_LOCALE__\n'
locale 2>/dev/null | head -5
printf '\n__SECURITY_SSH_CONFIG__\n'
grep -E '^(PermitRootLogin|PasswordAuthentication|PubkeyAuthentication|Port|AllowUsers|AllowGroups)' /etc/ssh/sshd_config 2>/dev/null || echo 'Cannot read sshd_config'
printf '\n__SECURITY_FIREWALL__\n'
ufw status 2>/dev/null || iptables -L -n --line-numbers 2>/dev/null | head -30 || firewall-cmd --list-all 2>/dev/null || echo 'No firewall tool detected'
printf '\n__SECURITY_FAILED_LOGINS__\n'
journalctl -u sshd --no-pager -n 20 --grep='Failed' 2>/dev/null || grep 'Failed' /var/log/auth.log 2>/dev/null | tail -10 || echo 'No failed login data'
printf '\n__SECURITY_OPEN_PORTS__\n'
ss -tlnp 2>/dev/null | head -25 || netstat -tlnp 2>/dev/null | head -25 || echo 'Cannot list ports'
"""

DISK_COMMAND = """
printf '__MOUNTS__\n'
df -kP 2>/dev/null | awk 'NR>1 {print $1"\t"$2"\t"$3"\t"$4"\t"$5"\t"$6}'
printf '__DIRS__\n'
if command -v timeout >/dev/null 2>&1; then
  timeout 12s sh -lc 'du -x -m -d 1 /var /home /srv /opt /tmp /usr/local 2>/dev/null | sort -nr | head -n 18'
else
  du -x -m -d 1 /var /home /srv /opt /tmp /usr/local 2>/dev/null | sort -nr | head -n 18
fi
printf '__LOGS__\n'
if [ -d /var/log ]; then
  if command -v timeout >/dev/null 2>&1; then
    timeout 10s sh -lc 'find /var/log -maxdepth 2 -type f -exec du -m {} + 2>/dev/null | sort -nr | head -n 12'
  else
    find /var/log -maxdepth 2 -type f -exec du -m {} + 2>/dev/null | sort -nr | head -n 12
  fi
fi
printf '__CLEANUP__\n'
if [ -d /tmp ]; then
  find /tmp -mindepth 1 -maxdepth 1 -mtime +7 2>/dev/null | head -n 12
fi
"""

NETWORK_COMMAND = """
if command -v ip >/dev/null 2>&1; then
  printf 'has_ip=1\n'
else
  printf 'has_ip=0\n'
fi
if command -v ss >/dev/null 2>&1; then
  printf 'has_ss=1\n'
else
  printf 'has_ss=0\n'
fi
printf '__LINKS__\n'
if command -v ip >/dev/null 2>&1; then
  ip -o link show 2>/dev/null
fi
printf '__ADDRS__\n'
if command -v ip >/dev/null 2>&1; then
  ip -o addr show 2>/dev/null
fi
printf '__ROUTES__\n'
if command -v ip >/dev/null 2>&1; then
  ip route show 2>/dev/null
elif command -v route >/dev/null 2>&1; then
  route -n 2>/dev/null
fi
printf '__LISTEN__\n'
if command -v ss >/dev/null 2>&1; then
  ss -lntupH 2>/dev/null | head -n 120
elif command -v netstat >/dev/null 2>&1; then
  netstat -lntup 2>/dev/null | tail -n +3 | head -n 120
fi
"""

SERVICE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.:@-]+(?:\.service)?$")
DOCKER_CONTAINER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
SERVICE_ACTIONS = {"start", "stop", "restart", "reload"}
PROCESS_ACTIONS = {"terminate", "kill_force"}
DOCKER_ACTIONS = {"start", "stop", "restart"}
LOG_SOURCES = {
    "journal": {
        "label": "System Journal",
        "description": "Recent lines from journalctl",
        "kind": "journal",
    },
    "service": {
        "label": "Service Journal",
        "description": "Logs for a specific systemd unit",
        "kind": "service",
    },
    "syslog": {
        "label": "syslog",
        "description": "/var/log/syslog",
        "kind": "file",
        "path": "/var/log/syslog",
    },
    "messages": {
        "label": "messages",
        "description": "/var/log/messages",
        "kind": "file",
        "path": "/var/log/messages",
    },
    "auth": {
        "label": "auth.log",
        "description": "/var/log/auth.log",
        "kind": "file",
        "path": "/var/log/auth.log",
    },
    "nginx_error": {
        "label": "nginx error",
        "description": "/var/log/nginx/error.log",
        "kind": "file",
        "path": "/var/log/nginx/error.log",
    },
    "nginx_access": {
        "label": "nginx access",
        "description": "/var/log/nginx/access.log",
        "kind": "file",
        "path": "/var/log/nginx/access.log",
    },
    "apache_error": {
        "label": "apache error",
        "description": "/var/log/apache2/error.log or /var/log/httpd/error_log",
        "kind": "file",
        "path": ["/var/log/apache2/error.log", "/var/log/httpd/error_log"],
    },
    "apache_access": {
        "label": "apache access",
        "description": "/var/log/apache2/access.log or /var/log/httpd/access_log",
        "kind": "file",
        "path": ["/var/log/apache2/access.log", "/var/log/httpd/access_log"],
    },
}
APT_COMMON_PACKAGES = [
    "nginx",
    "docker.io",
    "docker-ce",
    "postgresql",
    "redis-server",
    "python3",
    "nodejs",
    "openssh-server",
]
RPM_COMMON_PACKAGES = [
    "nginx",
    "docker",
    "docker-ce",
    "postgresql-server",
    "redis",
    "python3",
    "nodejs",
    "openssh-server",
]
DOCKER_COMMAND = """
if command -v docker >/dev/null 2>&1; then
  printf 'has_docker=1\n'
  docker info >/dev/null 2>&1
  docker_ready=$?
  if [ "$docker_ready" -eq 0 ]; then
    printf 'docker_ready=1\n'
  else
    printf 'docker_ready=0\n'
  fi
else
  printf 'has_docker=0\n'
  printf 'docker_ready=0\n'
  docker_ready=127
fi
printf '__ERROR__\n'
if [ "${docker_ready:-0}" -ne 0 ] && command -v docker >/dev/null 2>&1; then
  docker info 2>&1 | head -n 20
fi
printf '__CONTAINERS__\n'
if [ "${docker_ready:-0}" -eq 0 ]; then
  docker ps -a --format '{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.State}}\t{{.Status}}\t{{.RunningFor}}\t{{.Ports}}' 2>/dev/null
fi
printf '__STATS__\n'
if [ "${docker_ready:-0}" -eq 0 ]; then
  docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}' 2>/dev/null
fi
"""
