FROM alpine:3.21

RUN apk add --no-cache ca-certificates squid \
    && addgroup -S -g 10003 ai-egress \
    && adduser -S -D -H -u 10003 -G ai-egress ai-egress \
    && install -d -o 10003 -g 10003 /var/cache/squid /var/log/squid /run/squid

COPY docker/ai-cli-egress-squid.conf /etc/squid/squid.conf
COPY --chmod=0755 docker/ai-cli-egress-entrypoint.sh /usr/local/bin/ai-cli-egress-entrypoint
USER 10003:10003
EXPOSE 3128
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD squidclient -h 127.0.0.1 -p 3128 mgr:info >/dev/null 2>&1 || exit 1
ENTRYPOINT ["/usr/local/bin/ai-cli-egress-entrypoint"]
