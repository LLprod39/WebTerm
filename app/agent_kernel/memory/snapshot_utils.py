from __future__ import annotations

import ast
import json
import re
import shlex
from typing import Any

from app.agent_kernel.memory.compaction import compact_text, extract_signal_lines, unique_preserving_order


def try_parse_list_literal(raw: str) -> list[str] | None:
    text = str(raw or "").strip()
    if not text or not (text.startswith("[") and text.endswith("]")):
        return None
    for loader in (json.loads, ast.literal_eval):
        try:
            parsed = loader(text)
        except Exception:
            continue
        if isinstance(parsed, (list, tuple)):
            return [str(item) for item in parsed if str(item or "").strip()]
    return None


def normalize_snapshot_lines(value: Any, *, limit: int = 6) -> list[str]:
    pending = list(value) if isinstance(value, (list, tuple, set)) else [value]
    normalized: list[str] = []
    while pending:
        current = pending.pop(0)
        if isinstance(current, (list, tuple, set)):
            pending = list(current) + pending
            continue
        raw = str(current or "").strip()
        if not raw:
            continue
        parsed_lines = try_parse_list_literal(raw)
        if parsed_lines is not None:
            pending = parsed_lines + pending
            continue
        for line in raw.splitlines():
            cleaned = compact_text(str(line).lstrip("- ").strip(), limit=220)
            if cleaned:
                normalized.append(cleaned)
    return unique_preserving_order(normalized, limit=limit)


def render_snapshot_lines(lines: Any, *, fallback: str) -> str:
    normalized = normalize_snapshot_lines(lines, limit=6)
    if not normalized:
        normalized = [fallback]
    return "\n".join(f"- {line}" for line in normalized[:6])


def tokenize_shell_command(command: str) -> list[str]:
    try:
        return shlex.split(str(command or ""))
    except Exception:
        return str(command or "").split()


def docker_run_summary(command: str) -> dict[str, Any]:
    tokens = tokenize_shell_command(command)
    if len(tokens) < 2 or tokens[0] != "docker" or tokens[1] != "run":
        return {}
    name = ""
    image = ""
    published_ports: list[str] = []
    skip_next = False
    for index in range(2, len(tokens)):
        token = tokens[index]
        if skip_next:
            skip_next = False
            continue
        if token in {"--name", "-p", "--publish", "-v", "--volume", "-e", "--env", "--network", "--restart", "-w", "--workdir"}:
            if index + 1 < len(tokens):
                value = tokens[index + 1]
                if token == "--name":
                    name = value
                if token in {"-p", "--publish"}:
                    published_ports.append(value)
            skip_next = True
            continue
        if token.startswith("--name="):
            name = token.split("=", 1)[1]
            continue
        if token.startswith("--publish="):
            published_ports.append(token.split("=", 1)[1])
            continue
        if token.startswith("-p") and token != "-p":
            published_ports.append(token[2:])
            continue
        if token.startswith("-"):
            continue
        image = token
        break
    return {
        "name": compact_text(name, limit=80),
        "image": compact_text(image, limit=80),
        "ports": [compact_text(item, limit=80) for item in published_ports if str(item or "").strip()],
    }


def extract_published_ports(blob: str) -> list[str]:
    matches = re.findall(r"(?:[\[\]0-9a-fA-F\.:]*:)?(\d+)->(\d+)\/([a-z]+)", str(blob or ""))
    return unique_preserving_order([f"{host}->{container}/{proto}" for host, container, proto in matches], limit=4)


def event_output_markers(event: Any) -> list[str]:
    raw_text = str(getattr(event, "raw_text_redacted", "") or "")
    if not raw_text:
        return []
    lines = raw_text.splitlines()
    if lines and lines[0].lstrip().startswith("$"):
        raw_text = "\n".join(lines[1:])
    return [compact_text(item, limit=140) for item in extract_signal_lines(raw_text, max_items=2)]


def derive_recent_event_points(events: list[Any]) -> dict[str, list[str]]:
    access_points: list[str] = []
    change_points: list[str] = []
    for event in events:
        payload = getattr(event, "structured_payload", None) or {}
        command = str(payload.get("command") or "").strip()
        if not command:
            continue
        command_lower = command.lower()
        output_markers = event_output_markers(event)
        published_ports = extract_published_ports("\n".join(output_markers))

        if command_lower.startswith("docker run "):
            summary = docker_run_summary(command)
            image = summary.get("image") or "unknown image"
            container_label = summary.get("name") or image
            ports = summary.get("ports") or published_ports
            port_text = ""
            if ports:
                normalized_ports = [item.replace("/tcp", "") for item in ports]
                port_text = "; опубликованы порты " + ", ".join(normalized_ports[:2])
                access_points.append(f"Docker publish: {container_label} доступен через {', '.join(normalized_ports[:2])}")
            change_points.append(f"Запущен контейнер {container_label} из {image}{port_text}")
            continue

        if "docker compose up" in command_lower:
            change_points.append(f"Выполнен rollout через `{compact_text(command, limit=120)}`")
            if published_ports:
                access_points.append("После compose подтверждены опубликованные порты: " + ", ".join(published_ports[:2]))
            continue

        if command_lower.startswith("docker rm ") or command_lower.startswith("docker rm -f"):
            target = tokenize_shell_command(command)[-1] if tokenize_shell_command(command) else "container"
            change_points.append(f"Удалён контейнер {compact_text(target, limit=80)}")
            continue

        if "systemctl restart nginx" in command_lower:
            change_points.append("Выполнен restart nginx")
            continue

        if "systemctl reload nginx" in command_lower:
            change_points.append("Выполнен reload nginx")
            continue

        if command_lower.startswith("docker ps") and published_ports:
            access_points.append("docker ps подтверждает опубликованные порты: " + ", ".join(published_ports[:2]))

    return {
        "access": unique_preserving_order(access_points, limit=4),
        "recent_changes": unique_preserving_order(change_points, limit=6),
    }


def content_delta(old_content: str, new_content: str) -> float:
    old_lines = {line.strip().lower() for line in str(old_content or "").splitlines() if line.strip()}
    new_lines = {line.strip().lower() for line in str(new_content or "").splitlines() if line.strip()}
    if not old_lines and not new_lines:
        return 0.0
    if not old_lines or not new_lines:
        return 1.0
    return 1.0 - (len(old_lines & new_lines) / max(len(old_lines | new_lines), 1))


def guess_memory_key(*, title: str, category: str | None, content: str) -> str:
    blob = f"{title}\n{category or ''}\n{content}".lower()
    if any(term in blob for term in ("vpn", "bastion", "jump host", "gateway", "ssh ", "sudo")):
        return "access"
    if any(term in blob for term in ("risk", "issue", "critical", "warning", "degrad", "incident", "alert", "fail")):
        return "risks"
    if any(term in blob for term in ("runbook", "checklist", "command", "verify", "systemctl", "docker", "journalctl")):
        return "runbook"
    if any(term in blob for term in ("change", "updated", "deployed", "restart", "reload", "migrat")):
        return "recent_changes"
    if category in {"security", "network"}:
        return "access"
    if category in {"issues", "performance", "storage"}:
        return "risks"
    if category == "solutions":
        return "runbook"
    return "profile"
