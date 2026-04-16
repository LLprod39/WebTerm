"""
One-shot script: creates the Full DevOps Autopilot mega-pipeline.
Run from mini_prod root:  python create_mega_pipeline.py
"""
import os
import sys

import django

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_ui.settings")
django.setup()

from django.contrib.auth.models import User

from studio.models import Pipeline

user = User.objects.filter(is_superuser=True).first()
if not user:
    print("ERROR: no superuser found")
    sys.exit(1)

# ── NODES ──────────────────────────────────────────────────────────────────
nodes = [
    # ── Trigger ──────────────────────────────────────────────────────────
    {
        "id": "t1", "type": "trigger/schedule",
        "position": {"x": 520, "y": 0},
        "data": {"label": "Daily Autopilot 04:00", "cron_expression": "0 4 * * *"},
    },

    # ── Phase 1: Parallel data collection (5 SSH nodes) ──────────────────
    {
        "id": "s_disk", "type": "agent/ssh_cmd",
        "position": {"x": 0, "y": 160},
        "data": {
            "label": "💾 Disk & Inodes",
            "command": (
                "df -h && echo '---INODES---' && df -i && "
                "echo '---LARGEST---' && du -sh /var/log /tmp /home 2>/dev/null | sort -hr | head -10"
            ),
        },
    },
    {
        "id": "s_mem", "type": "agent/ssh_cmd",
        "position": {"x": 260, "y": 160},
        "data": {
            "label": "🧠 CPU / Memory",
            "command": (
                "uptime && echo '---MEM---' && free -h && "
                "echo '---TOP_CPU---' && ps aux --sort=-%cpu | head -12 && "
                "echo '---TOP_MEM---' && ps aux --sort=-%mem | head -8"
            ),
        },
    },
    {
        "id": "s_svc", "type": "agent/ssh_cmd",
        "position": {"x": 520, "y": 160},
        "data": {
            "label": "⚙️ Services Status",
            "command": (
                "systemctl list-units --state=failed --no-pager 2>/dev/null | head -20 || echo 'systemd N/A' && "
                "echo '---RUNNING---' && systemctl list-units --state=running --no-pager 2>/dev/null | head -20 || true && "
                "echo '---KERNEL---' && uname -a && echo '---REBOOT---' && "
                "[ -f /var/run/reboot-required ] && cat /var/run/reboot-required || echo 'no reboot pending'"
            ),
        },
    },
    {
        "id": "s_sec", "type": "agent/ssh_cmd",
        "position": {"x": 780, "y": 160},
        "data": {
            "label": "🔒 Security Scan",
            "command": (
                "echo '=PORTS=' && ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null | head -20 && "
                "echo '=SSH_FAIL=' && grep 'Failed password' /var/log/auth.log 2>/dev/null | tail -15 || "
                "journalctl -u ssh --since '24 hours ago' 2>/dev/null | grep -i 'fail\\|invalid' | tail -15 || echo 'no auth log' && "
                "echo '=LAST=' && last | head -10"
            ),
        },
    },
    {
        "id": "s_logs", "type": "agent/ssh_cmd",
        "position": {"x": 1040, "y": 160},
        "data": {
            "label": "📋 Recent Errors",
            "command": (
                "echo '=SYSLOG_ERR=' && "
                "journalctl -p err --since '2 hours ago' --no-pager 2>/dev/null | tail -20 || "
                "grep -i 'error\\|crit\\|emerg' /var/log/syslog 2>/dev/null | tail -20 || echo 'no syslog' && "
                "echo '=DMESG_ERR=' && dmesg --level=err,crit 2>/dev/null | tail -10 || echo 'no dmesg'"
            ),
        },
    },

    # ── Phase 2: AI synthesis #1 ─────────────────────────────────────────
    {
        "id": "ai_triage", "type": "agent/llm_query",
        "position": {"x": 520, "y": 360},
        "data": {
            "label": "🧠 AI Triage & Scoring",
            "system_prompt": (
                "You are a senior SRE (Site Reliability Engineer). "
                "Analyse server telemetry and produce a short structured triage report. "
                "Always respond in Russian. Be concise and actionable."
            ),
            "prompt": (
                "Проанализируй следующие метрики сервера и дай оценку:\n\n"
                "## Диск\n{s_disk}\n\n## CPU/RAM\n{s_mem}\n\n"
                "## Сервисы\n{s_svc}\n\n## Безопасность\n{s_sec}\n\n## Ошибки\n{s_logs}\n\n"
                "Ответь строго в формате:\n"
                "SEVERITY: <число 1-10>\n"
                "CRITICAL: <да/нет>\n"
                "ISSUES:\n- <список проблем>\n"
                "ACTIONS:\n- <список немедленных действий>\n"
                "Если severity >= 7 или есть критические упавшие сервисы — добавь строку: FLAG:CRITICAL"
            ),
            "model": "gemini-2.0-flash-exp",
        },
    },

    # ── Phase 3: Branch on severity ──────────────────────────────────────
    {
        "id": "c_critical", "type": "logic/condition",
        "position": {"x": 520, "y": 530},
        "data": {
            "label": "🔴 Critical Issues?",
            "check_type": "contains",
            "check_value": "FLAG:CRITICAL",
        },
    },

    # ── Branch TRUE: Agent actually FIXES things ──────────────────────────
    {
        "id": "ai_plan", "type": "agent/llm_query",
        "position": {"x": 100, "y": 700},
        "data": {
            "label": "🧠 AI: Build Fix Plan",
            "system_prompt": "You are a Linux SRE. Generate EXACT shell commands to fix the identified problems. Each command must be safe to run non-interactively.",
            "prompt": (
                "На основе триажа:\n{ai_triage}\n\n"
                "Напиши конкретный план действий в виде bash-команд для исправления проблем.\n"
                "Формат ответа:\n"
                "FIX_PLAN:\n"
                "```bash\n"
                "# Restart failed services\n"
                "systemctl restart <service> 2>/dev/null || true\n"
                "# Clear temp/log space if needed\n"
                "journalctl --vacuum-size=200M 2>/dev/null || true\n"
                "# ... другие команды ...\n"
                "```\n"
                "Только безопасные команды! Не удалять данные приложений."
            ),
            "model": "gemini-2.0-flash-exp",
        },
    },
    {
        "id": "a_fix", "type": "agent/react",
        "position": {"x": 100, "y": 880},
        "data": {
            "label": "🤖 Agent: Execute Fixes",
            "goal": (
                "Ты SRE-агент. На основе плана исправлений от предыдущего шага: {ai_plan}\n\n"
                "Выполни следующие действия на сервере:\n"
                "1. Перезапусти упавшие systemd сервисы (если есть)\n"
                "2. Очисти journald логи если диск > 80%: journalctl --vacuum-size=200M\n"
                "3. Удали старые tmp файлы: find /tmp -mtime +3 -delete 2>/dev/null\n"
                "4. Проверь статус после каждого действия\n"
                "5. Составь отчёт о том, что было сделано и каков результат\n"
                "Используй инструмент выполнения команд. Сообщай о каждом шаге."
            ),
            "system_prompt": (
                "Ты автономный SRE-агент. Выполняй команды на сервере для исправления проблем. "
                "Действуй осторожно — только безопасные операции."
            ),
            "max_iterations": 8,
            "on_failure": "continue",
        },
    },
    {
        "id": "s_verify", "type": "agent/ssh_cmd",
        "position": {"x": 100, "y": 1060},
        "data": {
            "label": "✅ Verify Fixes",
            "command": (
                "echo '=FAILED_AFTER=' && systemctl list-units --state=failed --no-pager 2>/dev/null | head -10 || echo 'ok' && "
                "echo '=DISK_AFTER=' && df -h / /var 2>/dev/null && "
                "echo '=MEM_AFTER=' && free -h && "
                "echo '=REBOOT_REQUIRED=' && [ -f /var/run/reboot-required ] && echo 'REBOOT NEEDED' || echo 'no reboot'"
            ),
        },
    },
    {
        "id": "ai_fix_report", "type": "agent/llm_query",
        "position": {"x": 100, "y": 1220},
        "data": {
            "label": "🧠 AI: Fix Summary",
            "system_prompt": "You are an SRE writing an incident report. Be factual and precise. Respond in Russian.",
            "prompt": (
                "Составь отчёт об устранении инцидента:\n\n"
                "**Первоначальный тираж:**\n{ai_triage}\n\n"
                "**План исправлений:**\n{ai_plan}\n\n"
                "**Действия агента:**\n{a_fix}\n\n"
                "**Проверка после:**\n{s_verify}\n\n"
                "Формат:\n## Инцидент-репорт\n### Что было сломано\n### Что сделано\n### Текущий статус\n### Дальнейшие действия"
            ),
            "model": "gemini-2.0-flash-exp",
        },
    },

    # ── Branch FALSE: Routine maintenance + AI check ──────────────────────
    {
        "id": "s_maint", "type": "agent/ssh_cmd",
        "position": {"x": 940, "y": 700},
        "data": {
            "label": "🔧 Routine Maintenance",
            "command": (
                "echo '=PKG_UPDATE=' && apt-get update -qq 2>&1 | tail -3 || yum check-update -q 2>&1 | tail -3 || echo 'pkg update done' && "
                "echo '=JOURNAL_VACUUM=' && journalctl --vacuum-time=7d 2>/dev/null | tail -3 || echo 'ok' && "
                "echo '=TMP_CLEAN=' && find /tmp -mtime +1 -delete 2>/dev/null && echo 'tmp cleaned' && "
                "echo '=LOG_SIZE=' && du -sh /var/log 2>/dev/null"
            ),
        },
    },
    {
        "id": "ai_maint_check", "type": "agent/llm_query",
        "position": {"x": 940, "y": 880},
        "data": {
            "label": "🧠 AI: Maintenance Review",
            "system_prompt": "You are a DevOps engineer reviewing routine maintenance results. Respond in Russian.",
            "prompt": (
                "Сервер в норме. Посмотри результаты плановых работ:\n\n"
                "{s_maint}\n\n"
                "Также вот тираж (всё OK):\n{ai_triage}\n\n"
                "Составь краткий статус:\n"
                "## Плановое обслуживание выполнено\n"
                "- Что сделано\n- Метрики после\n- Рекомендации на следующую неделю\n"
                "STATUS: OK"
            ),
            "model": "gemini-2.0-flash-exp",
        },
    },

    # ── Phase 4: Executive summary (merges both branches) ────────────────
    {
        "id": "ai_exec", "type": "agent/llm_query",
        "position": {"x": 520, "y": 1380},
        "data": {
            "label": "🧠 AI: Executive Summary",
            "system_prompt": (
                "You are a CTO-level engineer writing a daily infrastructure digest. "
                "Respond in Russian. Use emojis for readability. Be brief but complete."
            ),
            "prompt": (
                "Напиши Executive Summary ежедневного состояния инфраструктуры.\n\n"
                "Тираж: {ai_triage}\n\n"
                "Данные о сервисах: {s_svc}\n\n"
                "Данные о безопасности: {s_sec}\n\n"
                "Используй формат:\n"
                "# 📊 Daily Infrastructure Report\n"
                "**Дата:** {timestamp}\n\n"
                "## 🟢/🔴 Общий статус\n"
                "## 💻 Инфраструктура\n"
                "## 🔒 Безопасность\n"
                "## ⚡ Производительность\n"
                "## 📋 Выполненные работы\n"
                "## 🎯 Рекомендации на завтра"
            ),
            "model": "gemini-2.0-flash-exp",
        },
    },

    # ── Phase 5: Outputs ──────────────────────────────────────────────────
    {
        "id": "o_report", "type": "output/report",
        "position": {"x": 260, "y": 1560},
        "data": {
            "label": "📋 Full Pipeline Report",
            "template": (
                "# Full DevOps Autopilot Report\n\n"
                "## Executive Summary\n{ai_exec}\n\n"
                "---\n## Disk Metrics\n```\n{s_disk}\n```\n\n"
                "## CPU/Memory\n```\n{s_mem}\n```\n\n"
                "## Services\n```\n{s_svc}\n```\n\n"
                "## Security\n```\n{s_sec}\n```\n\n"
                "## Error Log\n```\n{s_logs}\n```\n\n"
                "## AI Triage\n{ai_triage}"
            ),
        },
    },
    {
        "id": "o_email", "type": "output/email",
        "position": {"x": 680, "y": 1560},
        "data": {
            "label": "✉️ Email Report to Admin",
            "to_email": "admin@example.com",
            "subject": "🤖 Daily DevOps Autopilot Report",
            "body": (
                "# Daily DevOps Autopilot Report\n\n"
                "{ai_exec}\n\n"
                "---\n## AI Triage Details\n{ai_triage}"
            ),
        },
    },
    {
        "id": "o_slack", "type": "output/webhook",
        "position": {"x": 1060, "y": 1560},
        "data": {
            "label": "💬 Slack Notification",
            "url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
            "extra_payload": {"channel": "#devops-alerts", "username": "DevOps Autopilot"},
        },
    },
]

# ── EDGES ──────────────────────────────────────────────────────────────────
edges = [
    # Trigger → Phase 1 (fan-out to 5 parallel SSH)
    {"id": "e01", "source": "t1",      "target": "s_disk",  "animated": True},
    {"id": "e02", "source": "t1",      "target": "s_mem",   "animated": True},
    {"id": "e03", "source": "t1",      "target": "s_svc",   "animated": True},
    {"id": "e04", "source": "t1",      "target": "s_sec",   "animated": True},
    {"id": "e05", "source": "t1",      "target": "s_logs",  "animated": True},

    # Phase 1 → AI triage (fan-in)
    {"id": "e06", "source": "s_disk",  "target": "ai_triage", "animated": True},
    {"id": "e07", "source": "s_mem",   "target": "ai_triage", "animated": True},
    {"id": "e08", "source": "s_svc",   "target": "ai_triage", "animated": True},
    {"id": "e09", "source": "s_sec",   "target": "ai_triage", "animated": True},
    {"id": "e10", "source": "s_logs",  "target": "ai_triage", "animated": True},

    # AI triage → Condition
    {"id": "e11", "source": "ai_triage", "target": "c_critical", "animated": True},

    # Condition TRUE → Fix branch
    {"id": "e12", "source": "c_critical", "target": "ai_plan",  "sourceHandle": "true",  "animated": True},
    {"id": "e13", "source": "ai_plan",    "target": "a_fix",    "animated": True},
    {"id": "e14", "source": "a_fix",      "target": "s_verify", "animated": True},
    {"id": "e15", "source": "s_verify",   "target": "ai_fix_report", "animated": True},
    {"id": "e16", "source": "ai_fix_report", "target": "ai_exec", "animated": True},

    # Condition FALSE → Maintenance branch
    {"id": "e17", "source": "c_critical",   "target": "s_maint",       "sourceHandle": "false", "animated": True},
    {"id": "e18", "source": "s_maint",      "target": "ai_maint_check", "animated": True},
    {"id": "e19", "source": "ai_maint_check","target": "ai_exec",        "animated": True},

    # Executive summary → outputs
    {"id": "e20", "source": "ai_exec", "target": "o_report", "animated": True},
    {"id": "e21", "source": "ai_exec", "target": "o_email",  "animated": True},
    {"id": "e22", "source": "ai_exec", "target": "o_slack",  "animated": True},
]

# ── CREATE OR UPDATE ────────────────────────────────────────────────────────
name = "🤖 Full DevOps Autopilot"

existing = Pipeline.objects.filter(owner=user, name=name).first()
if existing:
    existing.nodes = nodes
    existing.edges = edges
    existing.description = (
        "Мега-пайплайн: 5 параллельных SSH + 4 запроса к LLM + ReAct-агент исправляет проблемы + "
        "плановое обслуживание + email-отчёт + Slack-уведомление. "
        "ИИ управляет всем циклом DevOps-автоматизации."
    )
    existing.icon = "🤖"
    existing.tags = ["autopilot", "ai", "email", "llm-query", "react-agent", "mega", "devops"]
    existing.save()
    print(f"Updated: {existing.id}")
else:
    p = Pipeline.objects.create(
        owner=user,
        name=name,
        description=(
            "Мега-пайплайн: 5 параллельных SSH + 4 запроса к LLM + ReAct-агент исправляет проблемы + "
            "плановое обслуживание + email-отчёт + Slack-уведомление. "
            "ИИ управляет всем циклом DevOps-автоматизации."
        ),
        icon="🤖",
        nodes=nodes,
        edges=edges,
        tags=["autopilot", "ai", "email", "llm-query", "react-agent", "mega", "devops"],
    )
    print(f"Created: {p.id} — {p.name} — {len(nodes)} nodes / {len(edges)} edges")
