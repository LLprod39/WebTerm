#!/bin/sh
set -eu

runtime_config=/tmp/squid.conf
cp /etc/squid/squid.conf "$runtime_config"

upstream_url=${AI_CLI_UPSTREAM_PROXY_URL:-}
if [ -n "$upstream_url" ]; then
    case "$upstream_url" in
        http://*) upstream_authority=${upstream_url#http://} ;;
        *) echo "AI_CLI_UPSTREAM_PROXY_URL must use http://host:port" >&2; exit 1 ;;
    esac

    case "$upstream_authority" in
        */*|*\?*|*\#*|*@*)
            echo "AI_CLI_UPSTREAM_PROXY_URL must not contain credentials, paths, queries, or fragments" >&2
            exit 1
            ;;
    esac

    upstream_host=${upstream_authority%:*}
    upstream_port=${upstream_authority##*:}
    if [ "$upstream_host" = "$upstream_authority" ] \
        || ! printf '%s' "$upstream_host" | grep -Eq '^[A-Za-z0-9.-]+$' \
        || ! printf '%s' "$upstream_port" | grep -Eq '^[0-9]{1,5}$' \
        || [ "$upstream_port" -lt 1 ] \
        || [ "$upstream_port" -gt 65535 ]; then
        echo "AI_CLI_UPSTREAM_PROXY_URL has an invalid host or port" >&2
        exit 1
    fi

    printf '\ncache_peer %s parent %s 0 no-query default\nnever_direct allow all\n' \
        "$upstream_host" "$upstream_port" >> "$runtime_config"
fi

exec squid --foreground -f "$runtime_config"
