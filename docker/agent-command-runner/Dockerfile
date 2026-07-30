FROM python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --no-cache-dir \
        "asyncssh==2.24.0" \
        "cffi==2.1.0" \
        "cryptography==49.0.0" \
        "pycparser==3.0" \
        "typing-extensions==4.16.0" \
    && useradd --create-home --uid 10001 runner

COPY docker/agent-command-runner/runner.py /opt/webterm/runner.py

USER 10001:10001
ENTRYPOINT ["python", "/opt/webterm/runner.py"]
