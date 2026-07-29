from __future__ import annotations

import os
from pathlib import Path

from .env_helpers import cli_command, env_bool, env_int, env_list, parse_cursor_cli_extra_env, parse_path_list_env

CURSOR_AVAILABLE_MODELS = [
    {"id": "auto", "name": "Auto", "description": "РђРІС‚РѕРјР°С‚РёС‡РµСЃРєРёР№ РІС‹Р±РѕСЂ Р»СѓС‡С€РµР№ РјРѕРґРµР»Рё"},
    {
        "id": "claude-4.5-sonnet",
        "name": "Claude 4.5 Sonnet",
        "description": "РЎР±Р°Р»Р°РЅСЃРёСЂРѕРІР°РЅРЅР°СЏ, 200k РєРѕРЅС‚РµРєСЃС‚",
    },
    {
        "id": "claude-4.5-opus",
        "name": "Claude 4.5 Opus",
        "description": "РЎР°РјР°СЏ РјРѕС‰РЅР°СЏ, 200k РєРѕРЅС‚РµРєСЃС‚",
    },
    {"id": "gpt-5.2", "name": "GPT-5.2", "description": "OpenAI, 272k РєРѕРЅС‚РµРєСЃС‚"},
    {"id": "gpt-5.2-codex", "name": "GPT-5.2 Codex", "description": "OpenAI Codex, 272k РєРѕРЅС‚РµРєСЃС‚"},
    {"id": "gemini-3-flash", "name": "Gemini 3 Flash", "description": "Google, Р±С‹СЃС‚СЂР°СЏ, 200k РєРѕРЅС‚РµРєСЃС‚"},
    {"id": "gemini-3-pro", "name": "Gemini 3 Pro", "description": "Google Pro, 200k РєРѕРЅС‚РµРєСЃС‚"},
    {"id": "grok-code", "name": "Grok Code", "description": "xAI, 256k РєРѕРЅС‚РµРєСЃС‚"},
    {"id": "composer-1", "name": "Composer 1", "description": "Cursor native, 200k РєРѕРЅС‚РµРєСЃС‚"},
    {"id": "composer-1.5", "name": "Composer 1.5", "description": "Cursor planning, 200k РєРѕРЅС‚РµРєСЃС‚"},
]

MODEL_RECOMMENDATIONS = {
    "simple": "gemini-3-flash",
    "standard": "claude-4.5-sonnet",
    "complex": "claude-4.5-opus",
    "debug": "gpt-5.2",
}


def _build_cli_runtime_config() -> dict[str, dict[str, object]]:
    return {
        "cursor": {
            "command": cli_command("CURSOR_CLI_PATH", "agent"),
            "args": [
                "-p",
                "--force",
                "--output-format",
                "stream-json",
                "--stream-partial-output",
                "--workspace",
                "{workspace}",
            ],
            "prompt_style": "positional",
            "allowed_args": ["model", "sandbox", "approve-mcps", "browser"],
        },
        "cursor_server": {
            "command": cli_command("CURSOR_CLI_PATH", "agent"),
            "args": [
                "-p",
                "--trust",
                "--output-format",
                "stream-json",
                "--stream-partial-output",
                "--workspace",
                "{workspace}",
                "--sandbox",
                "enabled",
            ],
            "prompt_style": "positional",
            "allowed_args": ["model", "approve-mcps"],
        },
        "cursor_plan": {
            "command": cli_command("CURSOR_CLI_PATH", "agent"),
            "args": ["-p", "--trust", "--mode=plan", "--output-format", "text", "--workspace", "{workspace}"],
            "prompt_style": "positional",
            "allowed_args": ["model"],
        },
        "claude": {
            "command": cli_command("CLAUDE_CLI_PATH", "claude"),
            "args": [
                "-p",
                "--verbose",
                "--output-format",
                "stream-json",
                "--include-partial-messages",
                "--dangerously-skip-permissions",
                "--debug",
                "mcp",
            ],
            "prompt_style": "positional",
            "allowed_args": [
                "model",
                "mcp-config",
                "allowedTools",
                "agent",
                "continue",
            ],
            "timeout_seconds": 1800,
        },
        "codex": {
            "command": cli_command("CODEX_CLI_PATH", "codex"),
            "args": ["exec", "--full-auto", "--cd", "{workspace}", "--skip-git-repo-check"],
            "prompt_style": "positional",
            "allowed_args": ["model", "sandbox"],
            "timeout_seconds": 1800,
        },
    }


def build_runtime_service_settings(*, base_dir: Path, agent_projects_dir: Path) -> dict[str, object]:
    raw_http1 = os.getenv("CURSOR_CLI_HTTP_1", "1").strip().lower()
    cursor_cli_http1 = raw_http1 not in ("0", "false", "no", "off")
    mars_codex_command = cli_command("MARS_CODEX_CLI_PATH", "codex")
    mars_gemini_command = cli_command("MARS_GEMINI_CLI_PATH", "gemini")
    return {
        "CLI_RUNTIME_TIMEOUT_SECONDS": int(os.getenv("CLI_RUNTIME_TIMEOUT_SECONDS", "600")),
        "CLI_FIRST_OUTPUT_TIMEOUT_SECONDS": int(os.getenv("CLI_FIRST_OUTPUT_TIMEOUT_SECONDS", "120")),
        "AGENT_ACTIVE_RUNS_PER_USER_LIMIT": env_int("AGENT_ACTIVE_RUNS_PER_USER_LIMIT", 5),
        "AGENT_ACTIVE_RUNS_GLOBAL_LIMIT": env_int("AGENT_ACTIVE_RUNS_GLOBAL_LIMIT", 25),
        "AGENT_RUN_STALE_SECONDS": env_int("AGENT_RUN_STALE_SECONDS", 21600),
        "PIPELINE_ACTIVE_RUNS_PER_USER_LIMIT": env_int("PIPELINE_ACTIVE_RUNS_PER_USER_LIMIT", 8),
        "PIPELINE_ACTIVE_RUNS_GLOBAL_LIMIT": env_int("PIPELINE_ACTIVE_RUNS_GLOBAL_LIMIT", 40),
        "PIPELINE_RUN_STALE_SECONDS": env_int("PIPELINE_RUN_STALE_SECONDS", 21600),
        "SSH_TERMINAL_SESSIONS_PER_USER_LIMIT": env_int("SSH_TERMINAL_SESSIONS_PER_USER_LIMIT", 12),
        "SSH_TERMINAL_SESSIONS_GLOBAL_LIMIT": env_int("SSH_TERMINAL_SESSIONS_GLOBAL_LIMIT", 120),
        "SSH_TERMINAL_SESSION_STALE_SECONDS": env_int("SSH_TERMINAL_SESSION_STALE_SECONDS", 180),
        "SSH_TERMINAL_SESSION_HEARTBEAT_SECONDS": env_int("SSH_TERMINAL_SESSION_HEARTBEAT_SECONDS", 30),
        "SSH_CONNECT_TIMEOUT_SECONDS": env_int("SSH_CONNECT_TIMEOUT_SECONDS", 10),
        "SSH_LOGIN_TIMEOUT_SECONDS": env_int("SSH_LOGIN_TIMEOUT_SECONDS", 20),
        "OS_DETECT_CONCURRENCY": env_int("OS_DETECT_CONCURRENCY", 4),
        "OS_DETECT_LOCK_SECONDS": env_int("OS_DETECT_LOCK_SECONDS", 30),
        "SSH_KEEPALIVE_INTERVAL_SECONDS": env_int("SSH_KEEPALIVE_INTERVAL_SECONDS", 20),
        "SSH_KEEPALIVE_COUNT_MAX": env_int("SSH_KEEPALIVE_COUNT_MAX", 3),
        # Monitoring freshness is a runtime contract shared by the status and
        # dashboard APIs.  Keep these values in settings instead of duplicating
        # endpoint-local defaults so operators can reason about one policy.
        "MONITORING_FULL_FAIL_METRICS_TRUST_SECONDS": env_int("MONITORING_FULL_FAIL_METRICS_TRUST_SECONDS", 300),
        "MONITORING_LIVE_CACHE_SECONDS": env_int("MONITORING_LIVE_CACHE_SECONDS", 300),
        "MONITORING_METRICS_REFRESH_COOLDOWN_SECONDS": env_int("MONITORING_METRICS_REFRESH_COOLDOWN_SECONDS", 90),
        "MCP_STDIO_INITIALIZE_TIMEOUT_SECONDS": env_int("MCP_STDIO_INITIALIZE_TIMEOUT_SECONDS", 20),
        "MCP_STDIO_REQUEST_TIMEOUT_SECONDS": env_int("MCP_STDIO_REQUEST_TIMEOUT_SECONDS", 30),
        "MCP_STDIO_TOOL_CALL_TIMEOUT_SECONDS": env_int("MCP_STDIO_TOOL_CALL_TIMEOUT_SECONDS", 120),
        "MCP_PROCESS_TERMINATE_TIMEOUT_SECONDS": env_int("MCP_PROCESS_TERMINATE_TIMEOUT_SECONDS", 2),
        "MCP_HTTP_CONNECT_TIMEOUT_SECONDS": env_int("MCP_HTTP_CONNECT_TIMEOUT_SECONDS", 10),
        "MCP_HTTP_REQUEST_TIMEOUT_SECONDS": env_int("MCP_HTTP_REQUEST_TIMEOUT_SECONDS", 30),
        "MCP_HTTP_TOOL_CALL_TIMEOUT_SECONDS": env_int("MCP_HTTP_TOOL_CALL_TIMEOUT_SECONDS", 120),
        "MCP_HTTP_RETRY_ATTEMPTS": env_int("MCP_HTTP_RETRY_ATTEMPTS", 2),
        "MCP_RUNNER_REQUEST_TIMEOUT_SECONDS": env_int("MCP_RUNNER_REQUEST_TIMEOUT_SECONDS", 120),
        "LLM_MAX_RETRY_ATTEMPTS": env_int("LLM_MAX_RETRY_ATTEMPTS", 3),
        "LLM_PROVIDER_TIMEOUT_SECONDS": env_int("LLM_PROVIDER_TIMEOUT_SECONDS", 90),
        "LLM_GEMINI_STREAM_TIMEOUT_SECONDS": env_int("LLM_GEMINI_STREAM_TIMEOUT_SECONDS", 90),
        "LLM_GROK_STREAM_TIMEOUT_SECONDS": env_int("LLM_GROK_STREAM_TIMEOUT_SECONDS", 3600),
        "LLM_GROK_REASONING_EFFORT": os.getenv("LLM_GROK_REASONING_EFFORT", "none").strip().lower(),
        "LLM_CLAUDE_STREAM_TIMEOUT_SECONDS": env_int("LLM_CLAUDE_STREAM_TIMEOUT_SECONDS", 120),
        "LLM_OPENAI_STREAM_TIMEOUT_SECONDS": env_int("LLM_OPENAI_STREAM_TIMEOUT_SECONDS", 90),
        "LLM_OPENAI_RESPONSES_TIMEOUT_SECONDS": env_int("LLM_OPENAI_RESPONSES_TIMEOUT_SECONDS", 300),
        "LLM_DAILY_TOKEN_LIMIT_PER_USER": env_int("LLM_DAILY_TOKEN_LIMIT_PER_USER", 0),
        "ANALYZE_TASK_BEFORE_RUN": os.getenv("ANALYZE_TASK_BEFORE_RUN", "1").strip().lower()
        in ("1", "true", "yes", "on"),
        "KUBERNETES_OPS_SYNC_INTERVAL_SECONDS": env_int("KUBERNETES_OPS_SYNC_INTERVAL_SECONDS", 300),
        "KUBERNETES_OPS_SYNC_MAX_BACKOFF_SECONDS": env_int("KUBERNETES_OPS_SYNC_MAX_BACKOFF_SECONDS", 1800),
        "KUBERNETES_OPS_STALE_AFTER_SECONDS": env_int("KUBERNETES_OPS_STALE_AFTER_SECONDS", 900),
        "KUBERNETES_OPS_AUDIT_RETENTION_DAYS": env_int("KUBERNETES_OPS_AUDIT_RETENTION_DAYS", 365),
        "KUBERNETES_OPS_READY_FOR_SIDEBAR": env_bool("KUBERNETES_OPS_READY_FOR_SIDEBAR", False),
        # Pilot: allow sidebar when runtime inventory is healthy even if
        # production-only release_scope evidence is still missing. Never use
        # for real production without READY_FOR_SIDEBAR + approval.
        "KUBERNETES_OPS_PILOT_SIDEBAR": env_bool("KUBERNETES_OPS_PILOT_SIDEBAR", False),
        "KUBERNETES_OPS_RELEASE_ENVIRONMENT": os.getenv("KUBERNETES_OPS_RELEASE_ENVIRONMENT", "local").strip().lower(),
        "KUBERNETES_OPS_PRODUCTION_APPROVAL_REF": os.getenv("KUBERNETES_OPS_PRODUCTION_APPROVAL_REF", "").strip(),
        "KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS": env_int(
            "KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS", 86400
        ),
        "KUBERNETES_ADMIN_MODE_ENABLED": env_bool("KUBERNETES_ADMIN_MODE_ENABLED", True),
        "KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED": env_bool("KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED", False),
        "KUBERNETES_ADMIN_BREAK_GLASS_APPLY_BYPASS_ENABLED": env_bool(
            "KUBERNETES_ADMIN_BREAK_GLASS_APPLY_BYPASS_ENABLED", False
        ),
        "KUBERNETES_ADMIN_DRY_RUN_PROOF_MAX_AGE_SECONDS": env_int(
            "KUBERNETES_ADMIN_DRY_RUN_PROOF_MAX_AGE_SECONDS", 1800
        ),
        "KUBERNETES_ADMIN_SECRET_READ_ENABLED": env_bool("KUBERNETES_ADMIN_SECRET_READ_ENABLED", False),
        "KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED": env_bool("KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED", False),
        "KUBERNETES_ADMIN_PATCH_MAX_BODY_BYTES": env_int("KUBERNETES_ADMIN_PATCH_MAX_BODY_BYTES", 65536),
        "KUBERNETES_ADMIN_NATIVE_SCALE_ENABLED": env_bool("KUBERNETES_ADMIN_NATIVE_SCALE_ENABLED", False),
        "KUBERNETES_ADMIN_NATIVE_RESTART_ENABLED": env_bool("KUBERNETES_ADMIN_NATIVE_RESTART_ENABLED", False),
        "KUBERNETES_ADMIN_SCALE_MAX_REPLICAS": env_int("KUBERNETES_ADMIN_SCALE_MAX_REPLICAS", 100),
        "KUBERNETES_ADMIN_NATIVE_DELETE_ENABLED": env_bool("KUBERNETES_ADMIN_NATIVE_DELETE_ENABLED", False),
        "KUBERNETES_ADMIN_DELETE_PROTECTED_NAMESPACES": [
            item.strip()
            for item in os.getenv(
                "KUBERNETES_ADMIN_DELETE_PROTECTED_NAMESPACES",
                "kube-system,kube-public,kube-node-lease,cattle-system,cattle-fleet-system,cattle-fleet-local-system,cert-manager,ingress-nginx,devtroncd,argocd,monitoring,logging,local",
            ).split(",")
            if item.strip()
        ],
        "KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED": env_bool(
            "KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED", False
        ),
        "KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED": env_bool(
            "KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED", False
        ),
        "KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED": env_bool("KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED", False),
        "KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED": env_bool("KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED", False),
        "KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED": env_bool("KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED", False),
        "KUBERNETES_ADMIN_EXEC_PROTECTED_NAMESPACES": [
            item.strip()
            for item in os.getenv(
                "KUBERNETES_ADMIN_EXEC_PROTECTED_NAMESPACES",
                "kube-system,kube-public,kube-node-lease,cattle-system,cattle-fleet-system,cattle-fleet-local-system,cert-manager,ingress-nginx,devtroncd,argocd,monitoring,logging,local",
            ).split(",")
            if item.strip()
        ],
        "KUBERNETES_ADMIN_EXEC_ALLOWED_COMMANDS": env_list(
            "KUBERNETES_ADMIN_EXEC_ALLOWED_COMMANDS",
            [
                "/bin/sh",
                "/bin/bash",
                "sh",
                "bash",
                "env",
                "printenv",
                "ls",
                "cat",
                "curl",
                "wget",
                "tail",
                "head",
                "grep",
                "sed",
                "awk",
                "ps",
                "df",
                "du",
                "whoami",
                "hostname",
                "uname",
                "stat",
            ],
        ),
        "KUBERNETES_ADMIN_EXEC_DENIED_COMMANDS": env_list(
            "KUBERNETES_ADMIN_EXEC_DENIED_COMMANDS",
            [
                "kubectl",
                "helm",
                "sudo",
                "su",
                "nsenter",
                "mount",
                "umount",
                "chroot",
                "iptables",
                "ip6tables",
                "nft",
                "ssh",
                "scp",
                "nc",
                "netcat",
                "socat",
                "docker",
                "crictl",
                "ctr",
                "nerdctl",
                "apk",
                "apt",
                "apt-get",
                "yum",
                "dnf",
                "rpm",
                "pip",
                "pip3",
                "python",
                "python3",
                "perl",
                "ruby",
                "node",
                "npm",
                "npx",
                "yarn",
                "pnpm",
                "dd",
                "mkfs",
                "reboot",
                "shutdown",
                "kill",
                "killall",
            ],
        ),
        "KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED": env_bool("KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED", False),
        "KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED": env_bool("KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED", False),
        "KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED": env_bool(
            "KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED", False
        ),
        "KUBERNETES_ADMIN_PORT_FORWARD_PROTECTED_NAMESPACES": [
            item.strip()
            for item in os.getenv(
                "KUBERNETES_ADMIN_PORT_FORWARD_PROTECTED_NAMESPACES",
                "kube-system,kube-public,kube-node-lease,cattle-system,cattle-fleet-system,cattle-fleet-local-system,cert-manager,ingress-nginx,devtroncd,argocd,monitoring,logging,local",
            ).split(",")
            if item.strip()
        ],
        "KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS": env_list("KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS", []),
        "KUBERNETES_ADMIN_PORT_FORWARD_MAX_DURATION_SECONDS": env_int(
            "KUBERNETES_ADMIN_PORT_FORWARD_MAX_DURATION_SECONDS", 900
        ),
        "KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF": os.getenv(
            "KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF", ""
        ).strip(),
        "KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED": env_bool("KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED", False),
        "KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED": env_bool(
            "KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED", False
        ),
        "KUBERNETES_ADMIN_NODE_DEBUG_ENABLED": env_bool("KUBERNETES_ADMIN_NODE_DEBUG_ENABLED", False),
        "KUBERNETES_ADMIN_NODE_DEBUG_RECORDING_ENABLED": env_bool(
            "KUBERNETES_ADMIN_NODE_DEBUG_RECORDING_ENABLED", False
        ),
        "KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF": os.getenv(
            "KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF", ""
        ).strip(),
        "KUBERNETES_ADMIN_INTERACTIVE_METADATA_RETENTION_DAYS": env_int(
            "KUBERNETES_ADMIN_INTERACTIVE_METADATA_RETENTION_DAYS", 365
        ),
        "KUBERNETES_ADMIN_INTERACTIVE_TRANSCRIPT_RETENTION_DAYS": env_int(
            "KUBERNETES_ADMIN_INTERACTIVE_TRANSCRIPT_RETENTION_DAYS", 30
        ),
        "KUBERNETES_ADMIN_TRANSCRIPT_EVENT_MAX_CHARS": env_int("KUBERNETES_ADMIN_TRANSCRIPT_EVENT_MAX_CHARS", 2000),
        "KUBERNETES_ADMIN_TRANSCRIPT_EVENT_MAX_COUNT": env_int("KUBERNETES_ADMIN_TRANSCRIPT_EVENT_MAX_COUNT", 2000),
        "_raw_http1": raw_http1,
        "CURSOR_CLI_HTTP_1": cursor_cli_http1,
        "CURSOR_CLI_EXTRA_ENV": parse_cursor_cli_extra_env(cursor_cli_http1=cursor_cli_http1),
        "SKILLS_GLOBAL_RULES": os.getenv("SKILLS_GLOBAL_RULES", "").strip(),
        "SKILLS_MAX_CONTEXT_CHARS": int(os.getenv("SKILLS_MAX_CONTEXT_CHARS", "24000")),
        "STUDIO_SKILLS_DIRS": parse_path_list_env(
            "STUDIO_SKILLS_DIRS",
            [base_dir / "studio" / "skills"],
        ),
        "MARS_CODEX_COMMAND": mars_codex_command,
        "MARS_GEMINI_COMMAND": mars_gemini_command,
        "MARS_INTERVIEW_CODEX_COMMAND": os.getenv("MARS_INTERVIEW_CODEX_CLI_PATH") or mars_codex_command,
        "MARS_CODEX_HOME": Path(os.getenv("MARS_CODEX_HOME", str(Path.home() / ".mars_codex_home"))).expanduser(),
        "MARS_GEMINI_HOME": Path(os.getenv("MARS_GEMINI_HOME", str(Path.home() / ".gemini"))).expanduser(),
        "MARS_USER_WORKSPACES_ROOT": Path(
            os.getenv("MARS_USER_WORKSPACES_ROOT", str(agent_projects_dir / "mars_workspaces"))
        ).expanduser(),
        "MARS_CODEX_TIMEOUT_SECONDS": env_int("MARS_CODEX_TIMEOUT_SECONDS", 1800),
        "MARS_GEMINI_TIMEOUT_SECONDS": env_int("MARS_GEMINI_TIMEOUT_SECONDS", 900),
        "MARS_TEST_TIMEOUT_SECONDS": env_int("MARS_TEST_TIMEOUT_SECONDS", 900),
        "MARS_INTERVIEW_CODEX_TIMEOUT_SECONDS": env_int("MARS_INTERVIEW_CODEX_TIMEOUT_SECONDS", 180),
        "MARS_AGENT_RUNTIME": os.getenv("MARS_AGENT_RUNTIME", "docker").strip().lower(),
        "MARS_AGENT_DOCKER_COMMAND": os.getenv("MARS_AGENT_DOCKER_COMMAND", "docker"),
        "MARS_AGENT_DOCKER_IMAGE": os.getenv("MARS_AGENT_DOCKER_IMAGE", "webterm-mars-agent:latest"),
        "MARS_AGENT_DOCKER_NETWORK": os.getenv("MARS_AGENT_DOCKER_NETWORK", "bridge"),
        "MARS_AGENT_DOCKER_WORKDIR": os.getenv("MARS_AGENT_DOCKER_WORKDIR", "/workspace"),
        "MARS_AGENT_DOCKER_CODEX_COMMAND": os.getenv("MARS_AGENT_DOCKER_CODEX_COMMAND", "codex"),
        "MARS_AGENT_DOCKER_GEMINI_COMMAND": os.getenv("MARS_AGENT_DOCKER_GEMINI_COMMAND", "gemini"),
        "MARS_AGENT_DOCKER_CPUS": os.getenv("MARS_AGENT_DOCKER_CPUS", "2"),
        "MARS_AGENT_DOCKER_MEMORY": os.getenv("MARS_AGENT_DOCKER_MEMORY", "2g"),
        "MARS_AGENT_DOCKER_PIDS_LIMIT": env_int("MARS_AGENT_DOCKER_PIDS_LIMIT", 512),
        "MARS_AGENT_DOCKER_CODEX_HOME_VOLUME": os.getenv("MARS_AGENT_DOCKER_CODEX_HOME_VOLUME", ""),
        "MARS_AGENT_DOCKER_GEMINI_HOME_VOLUME": os.getenv("MARS_AGENT_DOCKER_GEMINI_HOME_VOLUME", ""),
        "MARS_DOCKER_CONTAINER_PATH_PREFIX": os.getenv("MARS_DOCKER_CONTAINER_PATH_PREFIX", ""),
        "MARS_DOCKER_HOST_PATH_PREFIX": os.getenv("MARS_DOCKER_HOST_PATH_PREFIX", ""),
        "CURSOR_AVAILABLE_MODELS": list(CURSOR_AVAILABLE_MODELS),
        "MODEL_RECOMMENDATIONS": dict(MODEL_RECOMMENDATIONS),
        "CLI_RUNTIME_CONFIG": _build_cli_runtime_config(),
    }
