# Thin rebuild: keep existing Antigravity CLI binary, refresh adapter code only.
FROM webterm-ai-cli-antigravity:rollback-bbf75a7c5630
USER root
COPY ai_cli_runner_manager/adapters/antigravity.py /app/ai_cli_runner_manager/adapters/antigravity.py
USER 10001:10001
