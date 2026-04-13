"""
Built-in pipeline templates for Agent Studio.

Each template defines nodes and edges in React Flow format.
Node types: trigger/manual, agent/react, agent/multi, agent/ssh_cmd,
            agent/llm_query, logic/condition, logic/wait, logic/human_approval,
            output/report, output/webhook, output/email, output/telegram
"""

from .webhook_smoke import WEBHOOK_SMOKE_TEMPLATE

PIPELINE_TEMPLATES = [
    WEBHOOK_SMOKE_TEMPLATE,
    # ------------------------------------------------------------------
    # 1. Healthcheck Sweep
    # ------------------------------------------------------------------
    {
        "slug": "healthcheck-sweep",
        "name": "Healthcheck Sweep",
        "description": "Checks CPU, RAM, disk and load on multiple servers, generates a health report.",
        "icon": "🏥",
        "category": "Monitoring",
        "tags": ["health", "monitoring", "multi-server"],
        "nodes": [
            {
                "id": "n1",
                "type": "trigger/manual",
                "position": {"x": 300, "y": 50},
                "data": {"label": "Start Health Check"},
            },
            {
                "id": "n2",
                "type": "agent/multi",
                "position": {"x": 300, "y": 180},
                "data": {
                    "label": "Multi-Server Health Agent",
                    "goal": "Check the health of all connected servers. For each server: 1) Check CPU usage (top -bn1), 2) Check RAM (free -h), 3) Check disk space (df -h), 4) Check system load (uptime). Report any anomalies (CPU>80%, RAM>90%, disk>85%).",
                    "system_prompt": "You are a DevOps monitoring agent. Be thorough but concise. Flag any concerning metrics.",
                    "max_iterations": 15,
                    "on_failure": "continue",
                },
            },
            {
                "id": "n3",
                "type": "output/report",
                "position": {"x": 300, "y": 320},
                "data": {"label": "Health Report"},
            },
        ],
        "edges": [
            {"id": "e1-2", "source": "n1", "target": "n2", "animated": True},
            {"id": "e2-3", "source": "n2", "target": "n3", "animated": True},
        ],
    },

    # ------------------------------------------------------------------
    # 2. Docker Deploy
    # ------------------------------------------------------------------
    {
        "slug": "docker-deploy",
        "name": "Docker Deploy",
        "description": "Pulls latest image, recreates container, verifies it's running.",
        "icon": "🐳",
        "category": "Deployment",
        "tags": ["docker", "deploy", "automation"],
        "nodes": [
            {
                "id": "n1",
                "type": "trigger/manual",
                "position": {"x": 300, "y": 50},
                "data": {"label": "Start Deploy"},
            },
            {
                "id": "n2",
                "type": "agent/react",
                "position": {"x": 300, "y": 180},
                "data": {
                    "label": "Deploy Agent",
                    "goal": "Deploy the application using Docker: 1) Pull latest image: docker pull {image_name}, 2) Stop old container: docker stop {container_name} || true, 3) Remove old container: docker rm {container_name} || true, 4) Start new container: docker run -d --name {container_name} --restart unless-stopped {image_name}, 5) Verify container is running: docker ps | grep {container_name}",
                    "system_prompt": "You are a deployment agent. Execute steps in order. On error, report immediately.",
                    "max_iterations": 10,
                    "on_failure": "abort",
                },
            },
            {
                "id": "n3",
                "type": "logic/condition",
                "position": {"x": 300, "y": 330},
                "data": {
                    "label": "Deploy OK?",
                    "check_type": "status_ok",
                },
            },
            {
                "id": "n4",
                "type": "output/report",
                "position": {"x": 150, "y": 470},
                "data": {"label": "Deploy Success Report"},
            },
            {
                "id": "n5",
                "type": "output/report",
                "position": {"x": 450, "y": 470},
                "data": {"label": "Deploy Failure Report"},
            },
        ],
        "edges": [
            {"id": "e1-2", "source": "n1", "target": "n2", "animated": True},
            {"id": "e2-3", "source": "n2", "target": "n3", "animated": True},
            {"id": "e3-4", "source": "n3", "target": "n4", "sourceHandle": "true", "label": "success"},
            {"id": "e3-5", "source": "n3", "target": "n5", "sourceHandle": "false", "label": "failed"},
        ],
    },

    # ------------------------------------------------------------------
    # 3. Log Cleanup
    # ------------------------------------------------------------------
    {
        "slug": "log-cleanup",
        "name": "Log Cleanup",
        "description": "Finds and removes old logs and temp files, frees up disk space.",
        "icon": "🧹",
        "category": "Maintenance",
        "tags": ["cleanup", "logs", "disk"],
        "nodes": [
            {
                "id": "n1",
                "type": "trigger/schedule",
                "position": {"x": 300, "y": 50},
                "data": {"label": "Weekly Cleanup", "cron_expression": "0 2 * * 0"},
            },
            {
                "id": "n2",
                "type": "agent/ssh_cmd",
                "position": {"x": 300, "y": 180},
                "data": {
                    "label": "Check Disk Before",
                    "command": "df -h / && echo '---' && du -sh /var/log/* 2>/dev/null | sort -rh | head -20",
                },
            },
            {
                "id": "n3",
                "type": "agent/react",
                "position": {"x": 300, "y": 330},
                "data": {
                    "label": "Cleanup Agent",
                    "goal": "Clean up old logs and temporary files to free disk space: 1) Find log files older than 30 days in /var/log and remove or compress them, 2) Clean /tmp of files older than 7 days, 3) Clean apt/yum cache if on Linux, 4) Report total space freed.",
                    "system_prompt": "You are a disk maintenance agent. Be conservative — only delete clearly old/temp files. Always verify before deleting.",
                    "max_iterations": 12,
                    "on_failure": "continue",
                },
            },
            {
                "id": "n4",
                "type": "output/report",
                "position": {"x": 300, "y": 490},
                "data": {"label": "Cleanup Report"},
            },
        ],
        "edges": [
            {"id": "e1-2", "source": "n1", "target": "n2", "animated": True},
            {"id": "e2-3", "source": "n2", "target": "n3", "animated": True},
            {"id": "e3-4", "source": "n3", "target": "n4", "animated": True},
        ],
    },

    # ------------------------------------------------------------------
    # 4. Incident Response
    # ------------------------------------------------------------------
    {
        "slug": "incident-response",
        "name": "Incident Response",
        "description": "Triggered by webhook alert — investigates the issue, collects diagnostics, generates a report.",
        "icon": "🚨",
        "category": "Incident",
        "tags": ["incident", "alert", "diagnostics"],
        "nodes": [
            {
                "id": "n1",
                "type": "trigger/webhook",
                "position": {"x": 300, "y": 50},
                "data": {"label": "Alert Received"},
            },
            {
                "id": "n2",
                "type": "agent/multi",
                "position": {"x": 300, "y": 180},
                "data": {
                    "label": "Incident Investigation Agent",
                    "goal": "Incident triggered: {alert_name} on {server_name}. Investigate: 1) Check system resources (CPU, RAM, disk), 2) Check relevant services status (systemctl status or docker ps), 3) Examine recent logs (journalctl -n 100 or app logs), 4) Check network connectivity, 5) Identify root cause, 6) Suggest remediation steps.",
                    "system_prompt": "You are an incident response agent. Act urgently but carefully. Document every finding.",
                    "max_iterations": 20,
                    "on_failure": "continue",
                },
            },
            {
                "id": "n3",
                "type": "output/report",
                "position": {"x": 200, "y": 350},
                "data": {"label": "Incident Report"},
            },
            {
                "id": "n4",
                "type": "output/webhook",
                "position": {"x": 420, "y": 350},
                "data": {
                    "label": "Notify Slack",
                    "url": "https://hooks.slack.com/services/YOUR/WEBHOOK/HERE",
                },
            },
        ],
        "edges": [
            {"id": "e1-2", "source": "n1", "target": "n2", "animated": True},
            {"id": "e2-3", "source": "n2", "target": "n3", "animated": True},
            {"id": "e2-4", "source": "n2", "target": "n4", "animated": True},
        ],
    },

    # ------------------------------------------------------------------
    # 5. Security Audit
    # ------------------------------------------------------------------
    {
        "slug": "security-audit",
        "name": "Security Audit",
        "description": "Checks open ports, outdated packages, SSH config, and sudo permissions.",
        "icon": "🔐",
        "category": "Security",
        "tags": ["security", "audit", "compliance"],
        "nodes": [
            {
                "id": "n1",
                "type": "trigger/manual",
                "position": {"x": 300, "y": 50},
                "data": {"label": "Start Security Audit"},
            },
            {
                "id": "n2",
                "type": "agent/react",
                "position": {"x": 300, "y": 180},
                "data": {
                    "label": "Security Audit Agent",
                    "goal": "Perform a security audit: 1) Check listening ports (ss -tlnp or netstat -tlnp), 2) Check for outdated packages with known CVEs (apt list --upgradable or yum check-update), 3) Check SSH config (/etc/ssh/sshd_config) for password auth and root login, 4) Check sudoers for overly broad permissions (cat /etc/sudoers), 5) Check for world-writable files in sensitive locations, 6) Report all findings with severity.",
                    "system_prompt": "You are a security auditor. Do NOT make any changes. Only audit and report. Classify findings as CRITICAL/HIGH/MEDIUM/LOW.",
                    "max_iterations": 15,
                    "on_failure": "continue",
                },
            },
            {
                "id": "n3",
                "type": "output/report",
                "position": {"x": 300, "y": 340},
                "data": {"label": "Security Report"},
            },
        ],
        "edges": [
            {"id": "e1-2", "source": "n1", "target": "n2", "animated": True},
            {"id": "e2-3", "source": "n2", "target": "n3", "animated": True},
        ],
    },

    # ------------------------------------------------------------------
    # 6. Service Restart with Verification
    # ------------------------------------------------------------------
    {
        "slug": "service-restart",
        "name": "Service Restart",
        "description": "Restarts a service, waits for it to come up, verifies it is healthy.",
        "icon": "🔄",
        "category": "Operations",
        "tags": ["service", "restart", "ops"],
        "nodes": [
            {
                "id": "n1",
                "type": "trigger/webhook",
                "position": {"x": 300, "y": 50},
                "data": {"label": "Restart Triggered"},
            },
            {
                "id": "n2",
                "type": "agent/react",
                "position": {"x": 300, "y": 180},
                "data": {
                    "label": "Service Restart Agent",
                    "goal": "Restart service {service_name}: 1) Check current status: systemctl status {service_name}, 2) Restart: systemctl restart {service_name}, 3) Wait 10 seconds, 4) Check status again, 5) If using HTTP: curl -sf http://localhost:{port}/health, 6) Report result.",
                    "system_prompt": "You are a service management agent. Be methodical. Always verify the service is healthy after restart.",
                    "max_iterations": 8,
                    "on_failure": "abort",
                },
            },
            {
                "id": "n3",
                "type": "logic/condition",
                "position": {"x": 300, "y": 330},
                "data": {
                    "label": "Service Up?",
                    "check_type": "status_ok",
                },
            },
            {
                "id": "n4",
                "type": "output/report",
                "position": {"x": 150, "y": 470},
                "data": {"label": "Success"},
            },
            {
                "id": "n5",
                "type": "output/webhook",
                "position": {"x": 450, "y": 470},
                "data": {
                    "label": "Alert: Service Down",
                    "url": "",
                },
            },
        ],
        "edges": [
            {"id": "e1-2", "source": "n1", "target": "n2", "animated": True},
            {"id": "e2-3", "source": "n2", "target": "n3"},
            {"id": "e3-4", "source": "n3", "target": "n4", "sourceHandle": "true"},
            {"id": "e3-5", "source": "n3", "target": "n5", "sourceHandle": "false"},
        ],
    },

    # ------------------------------------------------------------------
    # 7. Server Update with Human Approval
    # ------------------------------------------------------------------
    {
        "slug": "server-update-approval",
        "name": "Server Update with Human Approval",
        "description": (
            "Discovers available updates on a server, classifies them as safe or risky, "
            "sends an approval request via Email & Telegram, waits for your decision, "
            "schedules the update with a 20-minute warning, executes it, then runs "
            "automated service verification and delivers a final report."
        ),
        "icon": "🔄",
        "category": "Maintenance",
        "tags": ["update", "approval", "human-in-the-loop", "telegram", "email"],
        "nodes": [
            # ── Trigger ────────────────────────────────────────────────────────
            {
                "id": "n1",
                "type": "trigger/manual",
                "position": {"x": 400, "y": 40},
                "data": {
                    "label": "Start Update Pipeline",
                    "description": "Can also be set to trigger/webhook for Telegram bot integration",
                },
            },

            # ── Step 1: Discovery (target: backup-01 — select in node config) ─
            {
                "id": "n2",
                "type": "agent/react",
                "position": {"x": 400, "y": 160},
                "data": {
                    "label": "🔍 Discover System State (backup-01)",
                    "goal": (
                        "Collect comprehensive information about this server:\n"
                        "1. OS and kernel version: `uname -a && cat /etc/os-release`\n"
                        "2. Currently running critical services: "
                        "`systemctl list-units --type=service --state=running` or `docker ps`\n"
                        "3. Available package updates: `apt list --upgradable 2>/dev/null` "
                        "or `yum check-update 2>/dev/null || dnf check-update 2>/dev/null`\n"
                        "4. Current disk / memory state: `df -h && free -h`\n"
                        "5. Uptime and last reboot: `uptime && last reboot | head -5`\n"
                        "Compile everything into a structured report with clear sections."
                    ),
                    "system_prompt": (
                        "You are a DevOps discovery agent. Collect facts accurately — do NOT make any changes. "
                        "Output a clean structured Markdown report."
                    ),
                    "max_iterations": 12,
                    "on_failure": "continue",
                    "server_ids": [],
                },
            },

            # ── Step 2: Analysis + Plan ────────────────────────────────────────
            {
                "id": "n3",
                "type": "agent/llm_query",
                "position": {"x": 400, "y": 300},
                "data": {
                    "label": "🧠 Analyse & Build Update Plan",
                    "system_prompt": (
                        "You are a senior DevOps engineer responsible for safe update planning. "
                        "Be conservative: when in doubt, classify an update as RISKY."
                    ),
                    "prompt": (
                        "Below is the current state of the server collected by the discovery agent.\n\n"
                        "{n2_output}\n\n"
                        "## Your task\n"
                        "Analyse the available updates and produce a structured update plan in Markdown.\n\n"
                        "### Classification rules\n"
                        "- **SAFE to auto-apply:** security patches for libraries not directly used by "
                        "running services (e.g. libssl, libc, curl for a batch server), minor tool updates "
                        "(git, vim, htop), Python/pip packages that are not app dependencies.\n"
                        "- **RISKY — manual review required:** kernel updates (require reboot), "
                        "updates to packages used by *running* services (nginx, postgresql, redis, docker, "
                        "python3, nodejs, java, etc.), any update that changes a major version, "
                        "systemd or libc updates.\n\n"
                        "### Output format (strictly follow this)\n"
                        "```\n"
                        "## UPDATE PLAN\n\n"
                        "### ✅ SAFE UPDATES (will be applied automatically)\n"
                        "- package1 1.2.3 → 1.2.4 — reason\n"
                        "- ...\n\n"
                        "### ⚠️ RISKY UPDATES (require manual testing)\n"
                        "- package2 5.0 → 6.0 — reason: major version bump affects running nginx\n"
                        "- ...\n\n"
                        "### 🔴 RUNNING SERVICES THAT WILL BE AFFECTED\n"
                        "- List services that will need a restart\n\n"
                        "### 📋 ESTIMATED DOWNTIME\n"
                        "- Estimated time to apply safe updates: X minutes\n"
                        "- Services expected to restart: ...\n\n"
                        "### 🚫 EXCLUDED FROM THIS RUN\n"
                        "- Risky packages excluded and why\n"
                        "```\n"
                    ),
                    "include_all_outputs": False,
                    "provider": "openai",
                    "model": "gpt-5-mini",
                },
            },

            # ── Step 3: Human Approval (шаблоны писем редактируются в Studio) ─
            {
                "id": "n4",
                "type": "logic/human_approval",
                "position": {"x": 400, "y": 460},
                "data": {
                    "label": "👤 Ожидание вашего решения",
                    "to_email": "",
                    "email_subject": "Обновление сервера: нужно ваше решение (запуск #{run_id})",
                    "email_body": (
                        "Здравствуйте.\n\n"
                        "Пайплайн «Обновление сервера с подтверждением» собрал план обновлений и ждёт вашего решения.\n\n"
                        "Если одобрите — безопасные обновления применятся автоматически через 1 мин. Рискованные только в отчёте.\n\n"
                        "——— Отчёт и план ———\n\n{all_outputs}\n\n"
                        "——— Что сделать ———\n\n"
                        "Нажмите одну ссылку (достаточно один раз):\n\n"
                        "• ОДОБРИТЬ (запустить обновления):\n{approve_url}\n\n"
                        "• ОТКЛОНИТЬ (ничего не делать):\n{reject_url}\n\n"
                        "Ссылка действительна {timeout_minutes} мин.\n\n"
                        "С уважением,\nWEU Pipeline"
                    ),
                    "tg_bot_token": "",
                    "tg_chat_id": "",
                    "base_url": "",
                    "timeout_minutes": 120,
                    "message": (
                        "Обновление сервера: нужно ваше решение (запуск #{run_id}).\n\n"
                        "ОДОБРИТЬ: {approve_url}\n\nОТКЛОНИТЬ: {reject_url}\n\nДействует 120 мин."
                    ),
                    "smtp_host": "",
                    "smtp_user": "",
                    "smtp_password": "",
                    "from_email": "",
                },
            },

            # ── Timeout branch → report ────────────────────────────────────────
            {
                "id": "n4_check",
                "type": "output/report",
                "position": {"x": 400, "y": 620},
                "data": {
                    "label": "⏳ Approval Timed Out",
                    "template": (
                        "# Approval Timed Out\n\n"
                        "The operator did not answer within the configured approval window.\n\n"
                        "**Approval node status:**\n{n4_error}\n\n"
                        "**Proposed update plan:**\n{n3_output}"
                    ),
                },
            },

            # Rejected branch → report
            {
                "id": "n4_rejected",
                "type": "output/report",
                "position": {"x": 750, "y": 760},
                "data": {
                    "label": "❌ Update Rejected",
                    "template": (
                        "# Update Rejected\n\n"
                        "The update plan was rejected by the operator.\n\n"
                        "**Reason / response:**\n{n4_error}\n\n"
                        "**Plan that was proposed:**\n{n3_output}"
                    ),
                },
            },

            # ── Step 4: Parse response, adjust plan (OpenAI gpt-5-mini) ───────
            {
                "id": "n5",
                "type": "agent/llm_query",
                "position": {"x": 150, "y": 760},
                "data": {
                    "label": "📝 Finalise Update Plan",
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "system_prompt": (
                        "You are a DevOps update planner. Reconcile the original plan with the "
                        "operator's response and produce the FINAL list of packages to update."
                    ),
                    "prompt": (
                        "## Original update plan\n{n3_output}\n\n"
                        "## Operator's approval response\n{n4_output}\n\n"
                        "## Your task\n"
                        "1. If the operator approved with no changes — reproduce the SAFE UPDATES list as-is.\n"
                        "2. If they modified the plan (e.g. 'approve but skip X', 'also update Y') — "
                        "apply those modifications carefully.\n"
                        "3. Output a final YAML-like list ready for the execution agent:\n\n"
                        "```\n"
                        "FINAL_SAFE_UPDATES:\n"
                        "  - package1\n"
                        "  - package2\n\n"
                        "SERVICES_TO_RESTART:\n"
                        "  - nginx\n\n"
                        "OPERATOR_NOTES: |\n"
                        "  Any notes from the operator\n"
                        "```\n"
                    ),
                    "include_all_outputs": False,
                },
            },

            # ── Step 5: Notify — Update in 20 min (шаблоны редактируются в Studio) ─
            {
                "id": "n6a",
                "type": "output/email",
                "position": {"x": 0, "y": 920},
                "data": {
                    "label": "📧 Письмо: обновление через 1 мин",
                    "to_email": "",
                    "subject": "Обновление сервера начнётся через 1 минуту",
                    "body": (
                        "Здравствуйте.\n\n"
                        "Вы одобрили план обновлений. Установка начнётся через 1 минуту.\n\n"
                        "Кратко могут быть недоступны затрагиваемые сервисы.\n\n"
                        "——— Список пакетов к установке ———\n\n{n5_output}"
                    ),
                    "smtp_host": "",
                    "smtp_user": "",
                    "smtp_password": "",
                },
            },
            {
                "id": "n6b",
                "type": "output/telegram",
                "position": {"x": 300, "y": 920},
                "data": {
                    "label": "📱 TG: обновление через 1 мин",
                    "bot_token": "",
                    "chat_id": "",
                    "message": (
                        "Обновление сервера начнётся через 1 мин.\n\n"
                        "Список пакетов:\n{n5_output}"
                    ),
                },
            },

            # ── Step 6: Wait (1 min for quick test; change to 20 for production) ─
            {
                "id": "n7",
                "type": "logic/wait",
                "position": {"x": 150, "y": 1080},
                "data": {
                    "label": "⏱️ Wait 1 Minute",
                    "wait_minutes": 1,
                },
            },
            {
                "id": "n6_merge",
                "type": "logic/merge",
                "position": {"x": 150, "y": 980},
                "data": {
                    "label": "📎 Notification Join",
                    "mode": "all",
                },
            },

            # ── Step 7: Execute updates (same server: backup-01) ───────────────
            {
                "id": "n8",
                "type": "agent/react",
                "position": {"x": 150, "y": 1220},
                "data": {
                    "label": "🚀 Apply Updates (backup-01)",
                    "goal": (
                        "Apply the approved server updates according to this plan:\n\n"
                        "{n5_output}\n\n"
                        "Instructions:\n"
                        "1. Read the FINAL_SAFE_UPDATES list above.\n"
                        "2. Run the update command: `DEBIAN_FRONTEND=noninteractive apt-get install -y "
                        "<packages>` (or `yum install -y` / `dnf install -y` as appropriate).\n"
                        "3. After packages are installed, restart each service listed in SERVICES_TO_RESTART "
                        "using `systemctl restart <service>` (or `docker restart <container>`).\n"
                        "4. For each restarted service, verify it is running: "
                        "`systemctl is-active <service>` (should return 'active').\n"
                        "5. If any package fails to install, log the error and continue with the rest — "
                        "do NOT abort the entire run.\n"
                        "6. Report a summary: packages installed, services restarted, any errors."
                    ),
                    "system_prompt": (
                        "You are an autonomous update agent. Apply ONLY the packages listed in "
                        "FINAL_SAFE_UPDATES. Do not update anything else. Be safe and methodical. "
                        "Always verify services after restart."
                    ),
                    "max_iterations": 20,
                    "on_failure": "continue",
                    "server_ids": [],
                },
            },

            # ── Step 8: Notify — Update done, testing starting ─────────────────
            {
                "id": "n9a",
                "type": "output/email",
                "position": {"x": 0, "y": 1380},
                "data": {
                    "label": "📧 Письмо: обновление выполнено",
                    "to_email": "",
                    "subject": "Обновление сервера выполнено — запущена проверка сервисов",
                    "body": (
                        "Здравствуйте.\n\n"
                        "Установка одобренных пакетов завершена, сервисы перезапущены.\n\n"
                        "Сейчас выполняется автоматическая проверка сервисов. Итоговый отчёт придёт отдельным письмом.\n\n"
                        "——— Лог установки ———\n\n{n8_output}"
                    ),
                    "smtp_host": "",
                    "smtp_user": "",
                    "smtp_password": "",
                },
            },
            {
                "id": "n9b",
                "type": "output/telegram",
                "position": {"x": 300, "y": 1380},
                "data": {
                    "label": "📱 TG: обновление выполнено",
                    "bot_token": "",
                    "chat_id": "",
                    "message": (
                        "Обновление сервера выполнено. Запущена проверка сервисов.\n\n"
                        "Лог: {n8_output}"
                    ),
                },
            },

            # ── Step 9: Service verification (backup-01) ───────────────────────
            {
                "id": "n10",
                "type": "agent/react",
                "position": {"x": 150, "y": 1540},
                "data": {
                    "label": "🧪 Verify Services (backup-01)",
                    "goal": (
                        "Verify that all services which were running before the update are still healthy.\n\n"
                        "Services that were running before the update:\n{n2_output}\n\n"
                        "Services restarted during update:\n{n8_output}\n\n"
                        "For each service:\n"
                        "1. Check if it is running: `systemctl is-active <service>` or `docker ps | grep <name>`\n"
                        "2. If it has an HTTP endpoint, send a health check: `curl -sf --max-time 5 "
                        "http://localhost:<port>/health` or equivalent\n"
                        "3. Check for recent errors in logs: `journalctl -u <service> --since '5 min ago' "
                        "--no-pager | tail -20`\n"
                        "4. If a service is down: attempt one restart (`systemctl restart <service>`), "
                        "wait 10s, check again, then report.\n\n"
                        "Produce a clear verification report with PASS / FAIL per service."
                    ),
                    "system_prompt": (
                        "You are a post-update verification agent. Be thorough — check every service. "
                        "Classify each as PASS or FAIL. Attempt one auto-recovery for failed services."
                    ),
                    "max_iterations": 20,
                    "on_failure": "continue",
                    "server_ids": [],
                },
            },
            {
                "id": "n9_merge",
                "type": "logic/merge",
                "position": {"x": 150, "y": 1460},
                "data": {
                    "label": "📎 Verification Join",
                    "mode": "all",
                },
            },

            # ── Step 10: Final report (шаблон редактируется в Studio) ─────────
            {
                "id": "n11",
                "type": "output/report",
                "position": {"x": 150, "y": 1700},
                "data": {
                    "label": "📋 Итоговый отчёт",
                    "template": (
                        "# Отчёт об обновлении сервера\n\n"
                        "## 1. Сбор данных о системе\n{n2_output}\n\n"
                        "## 2. План обновлений\n{n3_output}\n\n"
                        "## 3. Решение оператора\n{n4_output}\n\n"
                        "## 4. Итоговый список к установке\n{n5_output}\n\n"
                        "## 5. Лог установки\n{n8_output}\n\n"
                        "## 6. Проверка сервисов после обновления\n{n10_output}"
                    ),
                },
            },

            # ── Step 11: Final notifications ───────────────────────────────────
            {
                "id": "n12a",
                "type": "output/email",
                "position": {"x": 0, "y": 1860},
                "data": {
                    "label": "📧 Итоговый отчёт (email)",
                    "to_email": "",
                    "subject": "Итоговый отчёт: обновление сервера — {pipeline_name}",
                    "body": (
                        "Здравствуйте.\n\n"
                        "Пайплайн обновления сервера завершён. Итоги ниже.\n\n"
                        "——— Выполненная установка ———\n\n{n8_output}\n\n"
                        "——— Проверка сервисов ———\n\n{n10_output}"
                    ),
                    "smtp_host": "",
                    "smtp_user": "",
                    "smtp_password": "",
                },
            },
            {
                "id": "n12b",
                "type": "output/telegram",
                "position": {"x": 300, "y": 1860},
                "data": {
                    "label": "📱 Итоговый отчёт (TG)",
                    "bot_token": "",
                    "chat_id": "",
                    "message": (
                        "Итоговый отчёт: обновление сервера ({pipeline_name}).\n\n"
                        "Установка: {n8_output}\n\nПроверка сервисов: {n10_output}"
                    ),
                },
            },
        ],
        "edges": [
            # Trigger → Discovery
            {"id": "e1-2", "source": "n1", "target": "n2", "animated": True},
            # Discovery → Analysis
            {"id": "e2-3", "source": "n2", "target": "n3", "animated": True},
            # Analysis → Human Approval
            {"id": "e3-4", "source": "n3", "target": "n4", "animated": True},
            # Human Approval → Condition
            {"id": "e4-timeout", "source": "n4", "target": "n4_check", "sourceHandle": "timeout", "animated": True},
            # Condition → Rejected branch
            {"id": "e_check_rej", "source": "n4", "target": "n4_rejected", "sourceHandle": "rejected", "label": "rejected"},
            # Condition → Finalise plan (approved branch)
            {"id": "e_check_ok", "source": "n4", "target": "n5", "sourceHandle": "approved", "label": "approved"},
            # Finalise plan → Schedule notifications (parallel)
            {"id": "e5-6a", "source": "n5", "target": "n6a", "animated": True},
            {"id": "e5-6b", "source": "n5", "target": "n6b", "animated": True},
            # Both notifications → Wait
            {"id": "e6a-merge", "source": "n6a", "target": "n6_merge", "sourceHandle": "success", "animated": True},
            {"id": "e6b-merge", "source": "n6b", "target": "n6_merge", "sourceHandle": "success", "animated": True},
            {"id": "e6merge-7", "source": "n6_merge", "target": "n7", "sourceHandle": "out", "animated": True},
            # Wait → Execute updates
            {"id": "e7-8", "source": "n7", "target": "n8", "sourceHandle": "done", "animated": True},
            # Execute → Done notifications (parallel)
            {"id": "e8-9a", "source": "n8", "target": "n9a", "animated": True},
            {"id": "e8-9b", "source": "n8", "target": "n9b", "animated": True},
            # Both notifications → Service verification
            {"id": "e9a-merge", "source": "n9a", "target": "n9_merge", "sourceHandle": "success", "animated": True},
            {"id": "e9b-merge", "source": "n9b", "target": "n9_merge", "sourceHandle": "success", "animated": True},
            {"id": "e9merge-10", "source": "n9_merge", "target": "n10", "sourceHandle": "out", "animated": True},
            # Verification → Final report
            {"id": "e10-11", "source": "n10", "target": "n11", "animated": True},
            # Final report → Final notifications (parallel)
            {"id": "e11-12a", "source": "n11", "target": "n12a", "animated": True},
            {"id": "e11-12b", "source": "n11", "target": "n12b", "animated": True},
        ],
    },

    # ------------------------------------------------------------------
    # 8. Certificate Expiry Check (was 7)
    # ------------------------------------------------------------------
    {
        "slug": "cert-expiry-check",
        "name": "Certificate Expiry Check",
        "description": "Checks SSL certificate expiry on configured domains, alerts if < 30 days.",
        "icon": "🔒",
        "category": "Security",
        "tags": ["ssl", "certificates", "monitoring"],
        "nodes": [
            {
                "id": "n1",
                "type": "trigger/schedule",
                "position": {"x": 300, "y": 50},
                "data": {"label": "Daily Check", "cron_expression": "0 8 * * *"},
            },
            {
                "id": "n2",
                "type": "agent/react",
                "position": {"x": 300, "y": 180},
                "data": {
                    "label": "Cert Check Agent",
                    "goal": "Check SSL certificate expiry: For each domain in {domains}: run 'echo | openssl s_client -connect {domain}:443 2>/dev/null | openssl x509 -noout -dates'. Calculate days until expiry. Flag any certificate expiring within 30 days.",
                    "system_prompt": "You are a certificate monitoring agent. Be precise with date calculations.",
                    "max_iterations": 10,
                    "on_failure": "continue",
                },
            },
            {
                "id": "n3",
                "type": "logic/condition",
                "position": {"x": 300, "y": 330},
                "data": {
                    "label": "Any Expiring Soon?",
                    "check_type": "contains",
                    "check_value": "EXPIRING SOON",
                },
            },
            {
                "id": "n4",
                "type": "output/webhook",
                "position": {"x": 150, "y": 470},
                "data": {
                    "label": "Alert Team",
                    "url": "",
                },
            },
            {
                "id": "n5",
                "type": "output/report",
                "position": {"x": 450, "y": 470},
                "data": {"label": "All OK Report"},
            },
        ],
        "edges": [
            {"id": "e1-2", "source": "n1", "target": "n2", "animated": True},
            {"id": "e2-3", "source": "n2", "target": "n3"},
            {"id": "e3-4", "source": "n3", "target": "n4", "sourceHandle": "true"},
            {"id": "e3-5", "source": "n3", "target": "n5", "sourceHandle": "false"},
        ],
    },
]
