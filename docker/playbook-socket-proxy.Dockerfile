FROM python:3.11.15-alpine

RUN addgroup -g 10002 socketproxy \
    && adduser -D -H -u 10002 -G socketproxy socketproxy

WORKDIR /proxy
COPY app/playbook_socket_proxy_policy.py ./playbook_socket_proxy_policy.py
COPY app/agent_command_socket_proxy_policy.py ./agent_command_socket_proxy_policy.py
COPY docker/playbook_socket_proxy.py ./playbook_socket_proxy.py

USER 10002:10002
EXPOSE 2375
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:2375/health', timeout=2).read()"
CMD ["python", "/proxy/playbook_socket_proxy.py"]
