"""
Mini-agent executor: runs configured commands on servers via SSH,
then sends output to LLM for analysis.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import asyncssh
from asgiref.sync import sync_to_async as _s2a


def sync_to_async(func, thread_sensitive=False):
    """Wrapper that defaults thread_sensitive=False to avoid CurrentThreadExecutor conflicts."""
    return _s2a(func, thread_sensitive=thread_sensitive)
from django.utils import timezone
from loguru import logger

from app.tools.safety import is_dangerous_command
from core_ui.activity import log_user_activity
from core_ui.audit import audit_context
from servers.models import AgentRun, Server, ServerAgent
from servers.monitor import _build_connect_kwargs

COMMAND_TIMEOUT = 30

AGENT_TEMPLATES: dict[str, dict[str, Any]] = {
    "security_audit": {
        "name": "Аудит безопасности",
        "commands": [
            "ss -tulnp 2>/dev/null || netstat -tulnp 2>/dev/null",
            "lastb -n 20 2>/dev/null || echo 'lastb not available'",
            "journalctl -u sshd --since '1 hour ago' --no-pager -q 2>/dev/null | tail -30 || true",
            "cat /etc/passwd | grep -v nologin | grep -v false | grep -v sync",
            "find /tmp /var/tmp -type f -perm /111 -mmin -60 2>/dev/null | head -20",
            "last -n 10 2>/dev/null || true",
        ],
        "ai_prompt": (
            "Ты — аудитор безопасности. Проанализируй вывод на предмет:\n"
            "- Подозрительных открытых портов или сервисов\n"
            "- Неудачных попыток входа или признаков брутфорса\n"
            "- Необычных учётных записей или недавних входов\n"
            "- Подозрительных файлов во временных директориях\n"
            "Оцени уровень риска: Низкий / Средний / Высокий / Критический."
        ),
    },
    "log_analyzer": {
        "name": "Анализ логов",
        "commands": [
            "journalctl -p 3 --since '1 hour ago' --no-pager -q 2>/dev/null | tail -40 || true",
            "dmesg --level=err,crit,alert -T 2>/dev/null | tail -20 || true",
            "tail -50 /var/log/syslog 2>/dev/null || tail -50 /var/log/messages 2>/dev/null || echo 'No syslog'",
            "tail -30 /var/log/nginx/error.log 2>/dev/null || echo 'No nginx error log'",
            "journalctl --since '1 hour ago' --no-pager -q 2>/dev/null | grep -iE 'error|fail|crit|panic|oom' | tail -20 || true",
        ],
        "ai_prompt": (
            "Ты — аналитик логов. Найди закономерности:\n"
            "- Повторяющиеся ошибки и их частота\n"
            "- Критические проблемы, требующие немедленного внимания\n"
            "- OOM-убийства, segfault-ы или падения сервисов\n"
            "- Практические рекомендации по исправлению проблем."
        ),
    },
    "performance": {
        "name": "Профиль производительности",
        "commands": [
            "cat /proc/loadavg",
            "free -m",
            "ps aux --sort=-%cpu --no-headers | head -10",
            "ps aux --sort=-%mem --no-headers | head -10",
            "iostat -x 1 1 2>/dev/null || echo 'iostat not available'",
            "ss -s 2>/dev/null || true",
            "vmstat 1 3 2>/dev/null || true",
        ],
        "ai_prompt": (
            "Ты — инженер по производительности. Проанализируй:\n"
            "- Узкие места CPU: какие процессы потребляют больше всего\n"
            "- Давление на память: есть ли использование swap, риск OOM\n"
            "- Производительность I/O: есть ли дисковые узкие места\n"
            "- Сетевые соединения: есть ли аномалии\n"
            "Предоставь конкретные рекомендации по оптимизации."
        ),
    },
    "disk_report": {
        "name": "Отчёт по дискам",
        "commands": [
            "df -h",
            "du -sh /* 2>/dev/null | sort -rh | head -15",
            "find /var/log -name '*.log' -size +50M 2>/dev/null | head -10",
            "find /tmp /var/tmp -type f -mtime +7 2>/dev/null | wc -l",
            "du -sh /var/log 2>/dev/null || true",
            "lsblk -f 2>/dev/null || true",
        ],
        "ai_prompt": (
            "Ты — аналитик хранилища. Составь отчёт:\n"
            "- Использование диска по разделам, какие близки к заполнению\n"
            "- Крупнейшие директории, занимающие место\n"
            "- Старые/большие лог-файлы для ротации или очистки\n"
            "- Временные файлы, которые можно безопасно удалить\n"
            "Предоставь рекомендации по очистке с оценкой экономии места."
        ),
    },
    "docker_status": {
        "name": "Статус Docker",
        "commands": [
            "docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Size}}' 2>/dev/null || echo 'Docker not available'",
            "docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}' 2>/dev/null || true",
            "docker system df 2>/dev/null || true",
            "docker ps -a --filter 'status=exited' --format '{{.Names}} ({{.Status}})' 2>/dev/null | head -10 || true",
            "docker images --format '{{.Repository}}:{{.Tag}}\t{{.Size}}' 2>/dev/null | head -15 || true",
        ],
        "ai_prompt": (
            "Ты — специалист по Docker/контейнерам. Проанализируй:\n"
            "- Здоровье контейнеров: запущенные, остановленные, перезапускающиеся\n"
            "- Использование ресурсов по контейнерам (CPU, память)\n"
            "- Дисковое пространство Docker (образы, тома, кэш сборки)\n"
            "- Остановленные контейнеры и висячие образы для очистки\n"
            "Предоставь команды `docker` для исправления проблем."
        ),
    },
    "service_health": {
        "name": "Здоровье сервисов",
        "commands": [
            "systemctl list-units --type=service --state=running --no-pager --plain 2>/dev/null | head -30",
            "systemctl list-units --type=service --state=failed --no-pager --plain 2>/dev/null || true",
            "systemctl list-units --type=service --state=inactive --no-pager --plain 2>/dev/null | head -15 || true",
            "journalctl -b --no-pager -q -p 3 2>/dev/null | grep -i 'service' | tail -15 || true",
        ],
        "ai_prompt": (
            "Ты — системный администратор. Проверь:\n"
            "- Какие критические сервисы запущены\n"
            "- Есть ли упавшие сервисы и почему они упали\n"
            "- Сервисы, которые должны работать, но не работают\n"
            "- Недавние ошибки, связанные с сервисами\n"
            "Предоставь команды `systemctl` для перезапуска/исправления упавших сервисов."
        ),
    },
}


FULL_AGENT_TEMPLATES: dict[str, dict[str, Any]] = {
    "security_patrol": {
        "name": "Патруль безопасности",
        "mode": "full",
        "goal": (
            "Провести комплексный аудит безопасности: просканировать открытые порты, проверить неудачные "
            "попытки входа, проверить учётные записи, инспектировать sudo/cron конфиги, проверить на "
            "руткиты/подозрительные процессы и составить приоритизированный отчёт по безопасности."
        ),
        "system_prompt": (
            "Ты — старший инженер по безопасности, проводящий систематический аудит.\n"
            "Работай методично: сеть -> аутентификация -> пользователи -> процессы -> файловая система.\n"
            "Оценивай каждую находку как Критическая/Высокая/Средняя/Низкая.\n"
            "Всегда проверяй типичные CVE и ошибки конфигурации.\n"
            "Отвечай и составляй отчёты на русском языке."
        ),
        "ai_prompt": "Патруль безопасности — автономный многоступенчатый аудит безопасности.",
        "commands": [],
        "stop_conditions": ["Все проверки безопасности завершены", "Найдена критическая уязвимость, требующая немедленных действий"],
    },
    "deploy_watcher": {
        "name": "Наблюдатель за деплоем",
        "mode": "full",
        "goal": (
            "Мониторить процесс деплоя: проверить здоровье сервисов до/после деплоя, "
            "следить за логами на предмет ошибок, проверить корректность ответов эндпоинтов и сообщить о проблемах. "
            "При появлении критических ошибок предложить шаги для отката."
        ),
        "system_prompt": (
            "Ты — инженер по деплою, мониторящий релиз.\n"
            "Проверяй статус сервисов, health-эндпоинты, частоту ошибок и использование ресурсов.\n"
            "Сравнивай состояние до и после деплоя.\n"
            "Если ошибки растут, расследуй причину и предложи откат.\n"
            "Отвечай и составляй отчёты на русском языке."
        ),
        "ai_prompt": "Наблюдатель за деплоем — мониторит развёртывание и ловит проблемы.",
        "commands": [],
        "stop_conditions": ["Деплой подтверждён как здоровый", "Рекомендован откат"],
    },
    "log_investigator": {
        "name": "Следователь по логам",
        "mode": "full",
        "goal": (
            "Расследовать недавние ошибки в системных и прикладных логах. Найти паттерны, "
            "соотнести события из разных источников логов, определить корневую причину и предоставить "
            "конкретные рекомендации по исправлению."
        ),
        "system_prompt": (
            "Ты — эксперт по анализу логов.\n"
            "Начни с journalctl/syslog для системных ошибок, затем проверь прикладные логи.\n"
            "Ищи паттерны: временные метки, коды ошибок, стектрейсы.\n"
            "Соотноси события между сервисами для поиска корневой причины.\n"
            "Отвечай и составляй отчёты на русском языке."
        ),
        "ai_prompt": "Следователь по логам — глубокий анализ логов для поиска корневых причин.",
        "commands": [],
        "stop_conditions": ["Корневая причина определена", "Значительных ошибок не обнаружено"],
    },
    "infra_scout": {
        "name": "Разведчик инфраструктуры",
        "mode": "full",
        "goal": (
            "Обследовать серверную инфраструктуру: версия ОС, установленные пакеты, запущенные сервисы, "
            "сетевая конфигурация, разметка дисков, Docker-контейнеры, задачи cron. "
            "Составить подробный профиль сервера."
        ),
        "system_prompt": (
            "Ты — специалист по документированию инфраструктуры.\n"
            "Систематически собирай: ОС, ядро, CPU, RAM, диски, сеть, сервисы, Docker, cron.\n"
            "Организуй находки в структурированный документ-профиль.\n"
            "Отвечай и составляй отчёты на русском языке."
        ),
        "ai_prompt": "Разведчик инфраструктуры — создаёт подробные профили серверов.",
        "commands": [],
        "stop_conditions": ["Профиль сервера готов"],
    },
    "multi_health": {
        "name": "Здоровье кластера",
        "mode": "full",
        "goal": (
            "Проверить здоровье всех подключённых серверов: CPU, память, диск, нагрузка, сервисы. "
            "Сравнить метрики между серверами, выявить аномалии и выбросы. "
            "Составить сводку по здоровью кластера."
        ),
        "system_prompt": (
            "Ты — монитор здоровья кластера.\n"
            "Проверяй каждый сервер: нагрузка, память, диск, упавшие сервисы, недавние ошибки.\n"
            "Сравнивай метрики между серверами для поиска выбросов.\n"
            "Отмечай любой сервер, значительно отклоняющийся от группы.\n"
            "Отвечай и составляй отчёты на русском языке."
        ),
        "ai_prompt": "Здоровье кластера — сравнительный анализ здоровья серверов.",
        "commands": [],
        "allow_multi_server": True,
        "stop_conditions": ["Все серверы проверены и сравнены"],
    },
}


def get_template(agent_type: str) -> dict[str, Any] | None:
    return AGENT_TEMPLATES.get(agent_type) or FULL_AGENT_TEMPLATES.get(agent_type)


def get_all_templates() -> list[dict[str, Any]]:
    result = []
    for key, tpl in AGENT_TEMPLATES.items():
        result.append({
            "type": key,
            "name": tpl["name"],
            "mode": "mini",
            "commands": tpl["commands"],
            "ai_prompt": tpl["ai_prompt"],
            "command_count": len(tpl["commands"]),
        })
    for key, tpl in FULL_AGENT_TEMPLATES.items():
        result.append({
            "type": key,
            "name": tpl["name"],
            "mode": "full",
            "goal": tpl.get("goal", ""),
            "system_prompt": tpl.get("system_prompt", ""),
            "ai_prompt": tpl.get("ai_prompt", ""),
            "commands": tpl.get("commands", []),
            "command_count": len(tpl.get("commands", [])),
            "allow_multi_server": tpl.get("allow_multi_server", False),
            "stop_conditions": tpl.get("stop_conditions", []),
        })
    return result


async def run_agent(agent: ServerAgent, server: Server, user) -> AgentRun:
    """Execute agent commands on a server and get AI analysis."""
    run = await sync_to_async(AgentRun.objects.create)(
        agent=agent,
        server=server,
        user=user,
        status=AgentRun.STATUS_RUNNING,
    )

    t0 = time.monotonic()
    commands = agent.commands or []
    outputs: list[dict[str, Any]] = []

    try:
        kwargs = await _build_connect_kwargs(server)
    except Exception as exc:
        run.status = AgentRun.STATUS_FAILED
        run.ai_analysis = f"Cannot connect to server: {exc}"
        run.completed_at = timezone.now()
        run.duration_ms = int((time.monotonic() - t0) * 1000)
        await sync_to_async(run.save)()
        return run

    try:
        async with asyncssh.connect(**kwargs) as conn:
            for cmd in commands:
                if is_dangerous_command(cmd):
                    outputs.append({
                        "cmd": cmd,
                        "stdout": "",
                        "stderr": "BLOCKED: dangerous command detected",
                        "exit_code": -1,
                        "duration_ms": 0,
                    })
                    continue

                cmd_t0 = time.monotonic()
                try:
                    result = await asyncio.wait_for(
                        conn.run(cmd, check=False),
                        timeout=COMMAND_TIMEOUT,
                    )
                    outputs.append({
                        "cmd": cmd,
                        "stdout": (result.stdout or "")[:5000],
                        "stderr": (result.stderr or "")[:2000],
                        "exit_code": result.exit_status,
                        "duration_ms": int((time.monotonic() - cmd_t0) * 1000),
                    })
                except asyncio.TimeoutError:
                    outputs.append({
                        "cmd": cmd,
                        "stdout": "",
                        "stderr": f"TIMEOUT after {COMMAND_TIMEOUT}s",
                        "exit_code": -1,
                        "duration_ms": COMMAND_TIMEOUT * 1000,
                    })
                except Exception as exc:
                    outputs.append({
                        "cmd": cmd,
                        "stdout": "",
                        "stderr": str(exc)[:500],
                        "exit_code": -1,
                        "duration_ms": int((time.monotonic() - cmd_t0) * 1000),
                    })
    except Exception as exc:
        run.status = AgentRun.STATUS_FAILED
        run.commands_output = outputs
        run.ai_analysis = f"SSH connection failed: {exc}"
        run.completed_at = timezone.now()
        run.duration_ms = int((time.monotonic() - t0) * 1000)
        await sync_to_async(run.save)()
        return run

    with audit_context(
        user_id=getattr(user, "id", None),
        username_snapshot=str(getattr(user, "username", "") or ""),
        channel="agent",
        path=f"/servers/api/agents/{agent.id}/run/",
        entity_type="agent_run",
        entity_id=str(run.id),
        entity_name=agent.name,
    ):
        ai_analysis = await _get_ai_analysis(agent, server, outputs)

    run.status = AgentRun.STATUS_COMPLETED
    run.commands_output = outputs
    run.ai_analysis = ai_analysis
    run.completed_at = timezone.now()
    run.duration_ms = int((time.monotonic() - t0) * 1000)
    await sync_to_async(run.save)()

    await sync_to_async(lambda: setattr(agent, "last_run_at", timezone.now()) or agent.save(update_fields=["last_run_at"]))()

    await sync_to_async(log_user_activity)(
        user=user,
        category="agent",
        action="agent_run",
        entity_type="agent",
        entity_id=str(agent.id),
        entity_name=agent.name,
        description=f"Ran '{agent.name}' on {server.name}: {run.status}",
        metadata={"server_id": server.id, "run_id": run.id, "duration_ms": run.duration_ms},
    )

    logger.info("Agent '{}' on {} -> {} ({}ms)", agent.name, server.name, run.status, run.duration_ms)
    return run


async def _get_ai_analysis(agent: ServerAgent, server: Server, outputs: list[dict]) -> str:
    from app.core.llm import LLMProvider

    tpl = get_template(agent.agent_type)
    system_prompt = (tpl or {}).get("ai_prompt", "")
    user_extra = agent.ai_prompt or ""

    prompt_parts = [
        f"# Agent: {agent.name}",
        f"Server: **{server.name}** ({server.host})",
        "",
    ]

    if system_prompt:
        prompt_parts.append(system_prompt)
        prompt_parts.append("")

    if user_extra:
        prompt_parts.append(f"Additional instructions: {user_extra}")
        prompt_parts.append("")

    prompt_parts.append("## Command outputs:\n")
    for i, out in enumerate(outputs, 1):
        prompt_parts.append(f"### Command {i}: `{out['cmd']}`")
        prompt_parts.append(f"Exit code: {out['exit_code']}")
        if out["stdout"]:
            prompt_parts.append(f"```\n{out['stdout'][:3000]}\n```")
        if out["stderr"]:
            prompt_parts.append(f"Stderr: `{out['stderr'][:500]}`")
        prompt_parts.append("")

    prompt_parts.extend([
        "---",
        "Предоставь краткий анализ в формате **Markdown** на русском языке:",
        "1. **Резюме** — 1-2 предложения об общем состоянии",
        "2. **Обнаружения** — ключевые проблемы, отсортированные по серьёзности",
        "3. **Рекомендации** — конкретные практические шаги",
        "4. **Уровень риска** — Низкий / Средний / Высокий / Критический",
        "",
        "Будь конкретным и практичным. Отвечай на русском языке.",
    ])

    full_prompt = "\n".join(prompt_parts)
    provider = LLMProvider()

    try:
        chunks = []
        async for chunk in provider.stream_chat(full_prompt, model="auto"):
            chunks.append(chunk)
        return "".join(chunks)
    except Exception as exc:
        logger.error("AI analysis failed for agent '{}': {}", agent.name, exc)
        return f"AI analysis failed: {exc}"


async def run_agent_on_all_servers(agent: ServerAgent, user) -> list[AgentRun]:
    """Run agent on all configured servers sequentially."""
    server_ids = await sync_to_async(lambda: list(agent.servers.values_list("id", flat=True)))()
    servers = await sync_to_async(lambda: list(Server.objects.filter(id__in=server_ids)))()

    runs = []
    for srv in servers:
        run = await run_agent(agent, srv, user)
        runs.append(run)
    return runs
