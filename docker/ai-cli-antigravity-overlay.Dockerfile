# Thin rebuild: keep existing Antigravity CLI binary, refresh runner Python code only.
FROM webterm-ai-cli-antigravity:rollback-bbf75a7c5630
USER root
COPY ai_cli_runner_manager/adapters/antigravity.py /app/ai_cli_runner_manager/adapters/antigravity.py
COPY ai_cli_runner_manager/adapters/antigravity_oauth.py /app/ai_cli_runner_manager/adapters/antigravity_oauth.py
COPY ai_cli_runner_manager/auth_input.py /app/ai_cli_runner_manager/auth_input.py
COPY ai_cli_runner_manager/provider_runtime.py /app/ai_cli_runner_manager/provider_runtime.py
USER 10001:10001
