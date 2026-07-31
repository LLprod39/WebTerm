FROM python:3.11.15-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 10001 runner

WORKDIR /opt/webterm
COPY docker/plugin-backend-runner/runner.py ./runner.py
COPY plugin_marketplace/sandbox_worker.py ./sandbox_worker.py
COPY plugin_marketplace/archive_paths.py ./archive_paths.py

USER 10001:10001
ENTRYPOINT ["python", "/opt/webterm/runner.py"]
