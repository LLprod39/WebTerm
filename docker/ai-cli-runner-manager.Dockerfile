FROM python:3.11.15-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/runner-manager

RUN groupadd --gid 10001 runner-manager \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin runner-manager

WORKDIR /app
COPY --from=docker:29.1.2-cli /usr/local/bin/docker /usr/local/bin/docker
COPY ai_cli_runner_manager/requirements.lock /app/ai_cli_runner_manager/requirements.lock
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --require-hashes -r /app/ai_cli_runner_manager/requirements.lock \
    && /opt/venv/bin/pip uninstall --yes pip setuptools wheel
ENV PATH="/opt/venv/bin:${PATH}"

COPY --chown=10001:10001 app/ai_runtime /app/app/ai_runtime
COPY --chown=10001:10001 ai_cli_runner_manager /app/ai_cli_runner_manager

USER 10001:10001
EXPOSE 9000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9000/health', timeout=4).read()"
CMD ["uvicorn", "ai_cli_runner_manager.server:app", "--host", "0.0.0.0", "--port", "9000"]
