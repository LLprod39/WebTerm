"""Inventory prose compression for Operator chat artifacts."""

from __future__ import annotations

import re
from typing import Any

from core_ui.models import ChatMessage

# Role-invention / fleet dump prose the model loves to write instead of using the UI card.
_INVENTORY_DUMP_MARKERS = re.compile(
    r"(?:"
    r"API\s*шлюз|"
    r"SSH\s*прокси|"
    r"CI/?CD|"
    r"staging\s+окружен|"
    r"веб\s+фронт|"
    r"тестов(ая|ая\s+сред)|"
    r"•\s*[\w.-]+(?:\s*,\s*[\w.-]+)+\s*[—–-]|"  # • a, b — role
    r"(?:^|\n)\s*[•\-\*]\s*(?:api|web|db|stg|ci|prom|redis|grafana|bastion|lunix)"
    r")",
    re.I | re.M,
)
_HOSTISH_BULLETS = re.compile(
    r"(?:^|\n)\s*(?:[•\-\*]|\d+\.)\s*.{0,40}(?:prod|stg|runner|primary|replica|grafana|lunix|bastion)",
    re.I,
)


def looks_like_inventory_prose_dump(content: str) -> bool:
    """True when the model listed fleet hosts/roles in text (UI card should own that)."""
    text = str(content or "").strip()
    if len(text) < 80:
        return False
    if _INVENTORY_DUMP_MARKERS.search(text):
        return True
    bullets = _HOSTISH_BULLETS.findall(text)
    if len(bullets) >= 3:
        return True
    # Many comma-separated host names on one line
    return len(re.findall(r"\b[\w-]+-(?:prod|stg|01|02)\b", text, flags=re.I)) >= 5


def short_inventory_line(*, count: int, status_counts: dict[str, Any] | None = None) -> str:
    sc = status_counts if isinstance(status_counts, dict) else {}
    healthy = int(sc.get("healthy") or 0)
    warning = int(sc.get("warning") or 0)
    critical = int(sc.get("critical") or 0)
    unreachable = int(sc.get("unreachable") or 0)
    unknown = int(sc.get("unknown") or 0)
    if count <= 0:
        count = healthy + warning + critical + unreachable + unknown
    parts = [f"{count} серверов"]
    if healthy and healthy == count:
        parts.append("все healthy")
    else:
        bits = []
        if healthy:
            bits.append(f"{healthy} ok")
        if warning:
            bits.append(f"{warning} warning")
        if critical:
            bits.append(f"{critical} critical")
        if unreachable:
            bits.append(f"{unreachable} unreachable")
        if unknown:
            bits.append(f"{unknown} unknown")
        if bits:
            parts.append(" · ".join(bits))
    return " · ".join(parts) + "."


def compress_inventory_assistant_content(message: ChatMessage) -> bool:
    """If inventory UI card is present and prose is a host dump, replace with one line.

    Returns True when content was rewritten. Platform-enforced so the model cannot
    spam role descriptions even if it ignores the system prompt.
    """
    if not message:
        return False
    meta = message.metadata if isinstance(message.metadata, dict) else {}
    tables = meta.get("tables") if isinstance(meta.get("tables"), list) else []
    servers_table = next(
        (t for t in tables if isinstance(t, dict) and t.get("kind") == "servers"),
        None,
    )
    if not servers_table and not meta.get("inventory_card"):
        return False
    content = message.content or ""
    host_tokens = len(re.findall(r"\b[\w-]+-\d{2}\b", content))
    if not looks_like_inventory_prose_dump(content) and host_tokens < 4:
        return False

    count = 0
    status_counts: dict[str, Any] | None = None
    if isinstance(servers_table, dict):
        status_counts = (
            servers_table.get("status_counts") if isinstance(servers_table.get("status_counts"), dict) else None
        )
        items = servers_table.get("items") if isinstance(servers_table.get("items"), list) else []
        count = len(items) or int(meta.get("inventory_count") or 0)
        title = str(servers_table.get("title") or "")
        m = re.search(r"(\d+)", title)
        if m and not count:
            count = int(m.group(1))
    if not count:
        count = int(meta.get("inventory_count") or 0)
    if not status_counts and isinstance(meta.get("inventory_status_counts"), dict):
        status_counts = meta["inventory_status_counts"]

    short = short_inventory_line(count=count, status_counts=status_counts)
    if (content or "").strip() == short:
        return False
    message.content = short
    message.metadata = {**meta, "inventory_prose_compressed": True}
    message.save(update_fields=["content", "metadata"])
    return True
