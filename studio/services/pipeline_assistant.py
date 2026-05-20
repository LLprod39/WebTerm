from __future__ import annotations

import asyncio
import json
import re
from difflib import SequenceMatcher
from typing import Any

from app.agent_kernel.memory.redaction import sanitize_prompt_context_text
from app.core.llm import LLMProvider

NODE_TYPE_CATALOG: dict[str, dict[str, Any]] = {
    "trigger/manual": {
        "category": "Triggers",
        "purpose": "Manual operator start. Use for test runs and human-launched workflows.",
        "source_handles": ["out"],
    },
    "trigger/webhook": {
        "category": "Triggers",
        "purpose": "HTTP POST start. Use when an external system starts a pipeline.",
        "source_handles": ["out"],
    },
    "trigger/schedule": {
        "category": "Triggers",
        "purpose": "Cron-like scheduled start.",
        "source_handles": ["out"],
    },
    "trigger/monitoring": {
        "category": "Triggers",
        "purpose": "Start from server monitoring alerts.",
        "source_handles": ["out"],
    },
    "agent/react": {
        "category": "Agents",
        "purpose": "Ops agent that reasons and uses server/tools according to policy.",
        "source_handles": ["success", "error", "out"],
    },
    "agent/multi": {
        "category": "Agents",
        "purpose": "Multi-server or multi-agent investigation step.",
        "source_handles": ["success", "error", "out"],
    },
    "agent/ssh_cmd": {
        "category": "Agents",
        "purpose": "Direct SSH command with preflight and verification commands.",
        "source_handles": ["success", "error", "out"],
    },
    "agent/llm_query": {
        "category": "Agents",
        "purpose": "Direct LLM reasoning step over previous outputs/context.",
        "source_handles": ["success", "error", "out"],
    },
    "agent/mcp_call": {
        "category": "Agents",
        "purpose": "Pinned MCP tool call with JSON arguments.",
        "source_handles": ["success", "error", "out"],
    },
    "logic/condition": {
        "category": "Logic",
        "purpose": "Branch by checking a prior node output.",
        "source_handles": ["true", "false"],
    },
    "logic/parallel": {
        "category": "Logic",
        "purpose": "Fan out work into parallel branches.",
        "source_handles": ["out"],
    },
    "logic/merge": {
        "category": "Logic",
        "purpose": "Join branches back together before continuing.",
        "source_handles": ["out"],
    },
    "logic/wait": {
        "category": "Logic",
        "purpose": "Pause execution for a configured duration.",
        "source_handles": ["done", "out"],
    },
    "logic/human_approval": {
        "category": "Logic",
        "purpose": "Pause until an operator approves/rejects/times out.",
        "source_handles": ["approved", "rejected", "timeout"],
    },
    "logic/telegram_input": {
        "category": "Logic",
        "purpose": "Ask an operator for a plain-text Telegram reply. This is not a trigger.",
        "source_handles": ["received", "timeout"],
    },
    "output/report": {
        "category": "Output",
        "purpose": "Generate a markdown report from prior node outputs.",
        "source_handles": ["success", "error", "out"],
    },
    "output/webhook": {
        "category": "Output",
        "purpose": "Send results to an external webhook.",
        "source_handles": ["success", "error", "out"],
    },
    "output/email": {
        "category": "Output",
        "purpose": "Send an email notification/report.",
        "source_handles": ["success", "error", "out"],
    },
    "output/telegram": {
        "category": "Output",
        "purpose": "Send a Telegram message. This does not wait for a reply.",
        "source_handles": ["success", "error", "out"],
    },
}

KNOWN_NODE_TYPES = set(NODE_TYPE_CATALOG)

NODE_TYPE_ALIASES = {
    "manual": "trigger/manual",
    "manual_trigger": "trigger/manual",
    "webhook": "trigger/webhook",
    "webhook_trigger": "trigger/webhook",
    "schedule": "trigger/schedule",
    "schedule_trigger": "trigger/schedule",
    "monitoring": "trigger/monitoring",
    "monitoring_trigger": "trigger/monitoring",
    "ssh_cmd": "agent/ssh_cmd",
    "ssh_command": "agent/ssh_cmd",
    "llm_query": "agent/llm_query",
    "mcp_call": "agent/mcp_call",
    "condition": "logic/condition",
    "parallel": "logic/parallel",
    "merge": "logic/merge",
    "wait": "logic/wait",
    "human_approval": "logic/human_approval",
    "telegram_input": "logic/telegram_input",
    "trigger/telegram_input": "logic/telegram_input",
    "input/telegram": "logic/telegram_input",
    "telegram/input": "logic/telegram_input",
    "telegram_trigger": "logic/telegram_input",
    "report": "output/report",
    "email": "output/email",
    "telegram": "output/telegram",
    "send_telegram": "output/telegram",
}

EDGE_PLACEHOLDER_TYPES = {
    "edge",
    "edge_placeholder",
    "connection",
    "graph_edge",
    "placeholder/edge",
}

HANDLE_ALIASES = {
    "yes": "true",
    "no": "false",
    "ok": "success",
    "done": "success",
    "approved": "approved",
    "rejected": "rejected",
    "timeout": "timeout",
    "reply": "received",
    "replied": "received",
    "received": "received",
}


class PipelineAssistantError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


_SYSTEM_PROMPT = """Ты — корпоративный AI copilot для Studio Pipeline Editor.

Ты помогаешь администратору проектировать, проверять и улучшать ВЕСЬ pipeline. Если передана focus node, ты можешь также дать точечный patch для неё.

Правила:
- Смотри на весь граф, а не только на одну ноду.
- Предлагай изменения с учетом реальных доступных ресурсов: servers, agent configs, MCP servers, skills.
- Если можно использовать существующий ресурс, ссылайся на него по точному ID.
- Если нужен точечный конфиг ноды, указывай target_node_id и заполняй node_patch только полями data этой ноды.
- Если пользователь хочет изменить несколько существующих шагов или убрать мусор из графа, используй graph_patch.update_nodes / remove_node_ids / remove_edge_ids.
- Если хочешь предложить новые шаги или ветку, используй graph_patch.nodes и graph_patch.edges.
- Если вопрос общий по pipeline, можешь оставить target_node_id пустым и дать только graph_patch и reply.
- Не удаляй существующие значения без явной просьбы пользователя.
- Для logic/condition обязательно учитывай source_node_id и входящие связи.
- Для agent/mcp_call предпочитай доступные MCP tools и валидные JSON arguments.
- Для agent/ssh_cmd избегай разрушительных команд; если действие потенциально опасное, добавляй human approval или явно предупреждай.
- Для agent/llm_query ОБЯЗАТЕЛЬНО заполняй data.prompt и data.system_prompt конкретными инструкциями: что прочитать из входов, как рассуждать, какой формат результата вернуть.
- Для agent/react и agent/multi ОБЯЗАТЕЛЬНО заполняй data.goal, data.system_prompt, data.instructions и data.expected_output. Нельзя оставлять AI-ноды пустыми или с общими словами вроде "process task".
- Промпты внутри AI-нод должны быть рабочими runbook-инструкциями: цель, входные данные, ограничения безопасности, формат ответа, что делать при недостатке данных.
- Работай в draft mode: ты предлагаешь изменения, но не считаешь их примененными до подтверждения оператора.
- Если запрос неоднозначен, задай 1-3 конкретных уточняющих вопроса в reply, но все равно предложи безопасный минимальный draft, если это возможно.
- reply должен быть коротким и практичным: что понял, что меняешь, что осталось проверить. Избегай длинных таблиц и воды.
- Если граф почти пустой или пользователь просит «собери пайплайн», верни готовый starter workflow, а не только советы.
- Возвращай только JSON-объект без markdown-обёрток, префиксов и пояснений вне JSON.

Верни ТОЛЬКО JSON-объект строго такого вида:
{
  "reply": "Markdown explanation for the operator",
  "target_node_id": null,
  "node_patch": {},
  "graph_patch": {
    "anchor_node_id": null,
    "nodes": [
      {
        "ref": "new_step_1",
        "type": "agent/llm_query",
        "label": "Optional human label",
        "data": {},
        "x_offset": 260,
        "y_offset": 0
      }
    ],
    "edges": [
      {
        "source": "existing_node_id_or_ref",
        "target": "existing_node_id_or_ref",
        "source_handle": "out",
        "label": ""
      }
    ],
    "update_nodes": [
      {
        "node_id": "existing_node_id",
        "data": {}
      }
    ],
    "remove_node_ids": [],
    "remove_edge_ids": []
  },
  "warnings": ["optional warning"],
  "patch_summary": "Short summary of the proposed graph changes",
  "suggested_next_actions": ["Save the pipeline", "Run a manual test"]
}

Правила для graph_patch:
- graph_patch.nodes / graph_patch.edges должны содержать только НОВЫЕ ноды и новые связи.
- В nodes[].ref используй короткие уникальные временные идентификаторы.
- В edges[].source / edges[].target можно ссылаться либо на существующий node_id, либо на ref из graph_patch.nodes.
- НИКОГДА не создавай ноду для связи. Связь всегда должна быть объектом в graph_patch.edges, а не node type "edge", "edge_placeholder" или "connection".
- Telegram Input — это строго logic/telegram_input. Не существует trigger/telegram_input.
- ШАБЛОН «Telegram-бот» (используй его при любом запросе про Telegram-автоматизацию):
  Шаг 1: trigger/webhook — ОБЯЗАТЕЛЬНЫЙ первый узел, точка входа для сообщений из Telegram.
  Шаг 2: agent/multi или agent/react — выполнение задачи пользователя (доступ к серверам).
  Шаг 3 (если нужны уточнения внутри одного запуска): output/telegram (задать вопрос) → logic/telegram_input (ждать ответа handle=received) → agent/... (продолжить с ответом).
  Шаг 4: output/telegram — финальный ответ пользователю.
  ВАЖНО: каждое новое сообщение пользователя = новый запуск через trigger/webhook. Пайплайн не зацикливается — это DAG.
  НИКОГДА не ставь logic/telegram_input первым узлом: это не trigger, он не может запустить пайплайн.
  НИКОГДА не создавай граф без trigger/manual, trigger/webhook, trigger/schedule или trigger/monitoring.
- Для правки существующих нод используй graph_patch.update_nodes.
- Для удаления существующих элементов используй remove_node_ids и remove_edge_ids.
- Если нужны только текстовые рекомендации без вставки в graph, оставляй graph_patch пустым.
- ОБЯЗАТЕЛЬНО: граф должен быть ациклическим (DAG). Циклы ЗАПРЕЩЕНЫ. Никогда не создавай edge, который указывает на узел-предок в цепочке. Если нужна повторная проверка по ответу пользователя — используй отдельный trigger (trigger/manual или trigger/monitoring), а не back-edge в основной граф.
- ОБЯЗАТЕЛЬНО: output/* и Telegram report ноды не должны вести обратно в предыдущие шаги. Для новых входящих задач от Telegram используй отдельный trigger/webhook или manual trigger, а не обратную связь из report в input.
- ОБЯЗАТЕЛЬНО: каждая новая нода должна быть достижима из какого-либо trigger-узла. Если добавляешь новую ветку, подключи её к существующему trigger или включи новый trigger-узел.
- ОБЯЗАТЕЛЬНО: для каждого edge указывай source_handle. Допустимые source_handle по типу ноды-источника:
  - trigger/* : "out"
  - logic/condition : "true" или "false"
  - logic/parallel : "out"
  - logic/merge : "out"
  - logic/wait : "done" или "out"
  - logic/human_approval : "approved", "rejected" или "timeout"
  - logic/telegram_input : "received" или "timeout"
  - agent/* : "success", "error" или "out"
  - output/* : "success", "error" или "out"
  - все остальные : "out"
- Используй только допустимые типы нод:
  trigger/manual, trigger/webhook, trigger/schedule, trigger/monitoring,
  agent/react, agent/multi, agent/ssh_cmd, agent/llm_query, agent/mcp_call,
  logic/condition, logic/parallel, logic/merge, logic/wait, logic/human_approval, logic/telegram_input,
  output/report, output/webhook, output/email, output/telegram"""


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    text = (raw_text or "").strip()
    if not text:
        return {}
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _prompt_json(value: object, *, limit: int) -> str:
    try:
        serialized = json.dumps(value, ensure_ascii=False, indent=2)
    except TypeError:
        serialized = json.dumps(str(value), ensure_ascii=False)
    sanitized = sanitize_prompt_context_text(serialized).text.strip()
    return sanitized[:limit] if len(sanitized) > limit else sanitized


def _node_catalog_payload() -> list[dict[str, Any]]:
    return [
        {
            "type": node_type,
            "category": item["category"],
            "purpose": item["purpose"],
            "source_handles": list(item["source_handles"]),
        }
        for node_type, item in NODE_TYPE_CATALOG.items()
    ]


def _warn(warnings: list[str] | None, message: str) -> None:
    if warnings is not None and message not in warnings:
        warnings.append(message)


def _humanize_ref(ref: str) -> str:
    return re.sub(r"[_\-]+", " ", str(ref or "").strip()).strip().title() or "AI Node"


def _canonical_node_type(raw_type: Any, *, ref: str, warnings: list[str] | None) -> str | None:
    node_type = str(raw_type or "").strip()
    lowered = node_type.lower()
    if lowered in KNOWN_NODE_TYPES:
        return lowered
    if lowered in NODE_TYPE_ALIASES:
        canonical = NODE_TYPE_ALIASES[lowered]
        _warn(warnings, f"AI node '{ref}' used type '{node_type}', normalized to '{canonical}'.")
        return canonical
    if lowered in EDGE_PLACEHOLDER_TYPES:
        _warn(warnings, f"AI node '{ref}' described an edge placeholder; it was converted to an edge or dropped.")
        return None
    _warn(warnings, f"AI node '{ref}' used unknown type '{node_type}' and was dropped.")
    return None


def _infer_structural_node_type(ref: str) -> str | None:
    value = str(ref or "").lower()
    if "parallel" in value or "fanout" in value or "fan_out" in value:
        return "logic/parallel"
    if "merge" in value or "join" in value:
        return "logic/merge"
    if "approval" in value or "approve" in value:
        return "logic/human_approval"
    if "telegram_input" in value or "operator_reply" in value:
        return "logic/telegram_input"
    if "wait" in value:
        return "logic/wait"
    return None


def _ref_tokens(ref: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9]+", str(ref or "").lower()) if part and part not in {"node", "step"}}


def _compact_ref(ref: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(ref or "").lower())


def _ref_digits(ref: str) -> set[str]:
    return set(re.findall(r"\d+", str(ref or "")))


def _resolve_graph_ref(raw_ref: str, known_refs: set[str]) -> str | None:
    ref = str(raw_ref or "").strip()
    if not ref:
        return None
    if ref in known_refs:
        return ref
    if not known_refs:
        return None

    ref_compact = _compact_ref(ref)
    compact_matches = [candidate for candidate in known_refs if _compact_ref(candidate) == ref_compact]
    if len(compact_matches) == 1:
        return compact_matches[0]

    tokens = _ref_tokens(ref)
    digits = _ref_digits(ref)
    scored: list[tuple[float, str]] = []
    for candidate in known_refs:
        candidate_tokens = _ref_tokens(candidate)
        candidate_digits = _ref_digits(candidate)
        token_score = len(tokens & candidate_tokens) / max(len(tokens), 1)
        digit_score = 0.25 if digits and digits <= candidate_digits else 0.0
        substring_score = 0.2 if ref_compact and ref_compact in _compact_ref(candidate) else 0.0
        similarity = SequenceMatcher(None, ref_compact, _compact_ref(candidate)).ratio()
        score = max(similarity, token_score + digit_score + substring_score)
        if score >= 0.72:
            scored.append((score, candidate))

    scored.sort(reverse=True)
    if len(scored) == 1:
        return scored[0][1]
    if len(scored) >= 2 and scored[0][0] - scored[1][0] >= 0.12:
        return scored[0][1]
    return None


def _allowed_source_handles(node_type: str) -> set[str]:
    catalog_item = NODE_TYPE_CATALOG.get(node_type)
    if catalog_item:
        return set(catalog_item["source_handles"])
    return {"out"}


def _default_source_handle(node_type: str) -> str:
    if node_type == "logic/condition":
        return "true"
    if node_type == "logic/human_approval":
        return "approved"
    if node_type == "logic/telegram_input":
        return "received"
    if node_type == "logic/wait":
        return "done"
    return "out"


def _normalize_source_handle(
    raw_handle: Any,
    *,
    source: str,
    source_type: str,
    warnings: list[str] | None,
) -> str:
    allowed = _allowed_source_handles(source_type)
    value = str(raw_handle or "").strip()
    if not value:
        return _default_source_handle(source_type)
    if value in allowed:
        return value
    alias = HANDLE_ALIASES.get(value.lower())
    if alias in allowed:
        _warn(warnings, f"AI edge from '{source}' used source_handle '{value}', normalized to '{alias}'.")
        return alias
    fallback = _default_source_handle(source_type)
    _warn(
        warnings,
        (
            f"AI edge from '{source}' used invalid source_handle '{value}' "
            f"for '{source_type or 'unknown'}', normalized to '{fallback}'."
        ),
    )
    return fallback


def _edge_from_placeholder_node(item: dict[str, Any]) -> dict[str, Any] | None:
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    ref = str(item.get("ref") or item.get("id") or "").strip()
    source = str(item.get("source") or data.get("source") or "").strip()
    target = str(item.get("target") or data.get("target") or "").strip()
    if not source and not target and "_to_" in ref:
        source, target = [part.strip() for part in ref.split("_to_", 1)]
    if not source or not target:
        return None
    return {
        "source": source,
        "target": target,
        "label": str(item.get("label") or data.get("label") or "").strip() or None,
        "source_handle": str(item.get("source_handle") or data.get("source_handle") or "").strip() or None,
        "target_handle": str(item.get("target_handle") or data.get("target_handle") or "").strip() or None,
    }


def _edge_path_exists(edges: list[dict[str, Any]], *, start: str, goal: str) -> bool:
    if not start or not goal:
        return False
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        if source and target:
            adjacency.setdefault(source, []).append(target)

    stack = [start]
    visited: set[str] = set()
    while stack:
        node = stack.pop()
        if node == goal:
            return True
        if node in visited:
            continue
        visited.add(node)
        stack.extend(adjacency.get(node, []))
    return False


def _append_ai_node(
    nodes: list[dict[str, Any]],
    new_node_types: dict[str, str],
    *,
    ref: str,
    node_type: str,
    label: str | None = None,
    data: dict[str, Any] | None = None,
    x_offset: float | None = None,
    y_offset: float | None = None,
) -> None:
    if ref in new_node_types:
        return
    nodes.append(
        {
            "ref": ref,
            "type": node_type,
            "data": data or {},
            "label": label or _humanize_ref(ref),
            "x_offset": x_offset,
            "y_offset": y_offset,
        }
    )
    new_node_types[ref] = node_type


def _ensure_ai_node_instructions(
    *,
    node_type: str,
    data: dict[str, Any],
    label: str,
    task_hint: str,
    warnings: list[str] | None,
) -> dict[str, Any]:
    if node_type not in {"agent/react", "agent/multi", "agent/llm_query"}:
        return data

    next_data = dict(data)
    node_label = label.strip() or "AI step"
    hint = task_hint.strip()
    short_hint = hint[:700] if hint else "the operator request and previous pipeline outputs"

    if node_type == "agent/llm_query":
        if not str(next_data.get("system_prompt") or "").strip():
            next_data["system_prompt"] = (
                "You are a concise DevOps automation analyst. Read the pipeline context and prior node outputs, "
                "avoid unsafe assumptions, and return a short actionable result with risks and next steps."
            )
            _warn(warnings, f"AI node '{node_label}' was missing system_prompt; a safe default was added.")
        if not str(next_data.get("prompt") or "").strip():
            next_data["prompt"] = (
                f"Task: {node_label}\n"
                f"Operator request: {short_hint}\n\n"
                "Use previous node outputs from the pipeline context. Produce:\n"
                "1. Brief conclusion.\n"
                "2. Important findings or missing data.\n"
                "3. Recommended next action.\n"
                "Keep the answer compact and suitable for Telegram/report output."
            )
            _warn(warnings, f"AI node '{node_label}' was missing prompt; a working prompt was added.")
        return next_data

    if not str(next_data.get("goal") or "").strip():
        next_data["goal"] = (
            f"{node_label}. Handle this automation task from the operator request: {short_hint}. "
            "Use only configured servers/tools, verify observations, and return a concise operational result."
        )
        _warn(warnings, f"AI node '{node_label}' was missing goal; a working goal was added.")
    if not str(next_data.get("system_prompt") or "").strip():
        next_data["system_prompt"] = (
            "You are a careful DevOps agent inside WebTermAI. Prefer read-only diagnostics first, "
            "avoid destructive commands without explicit approval, summarize evidence, and make every action auditable."
        )
        _warn(warnings, f"AI node '{node_label}' was missing system_prompt; a safe default was added.")
    if not str(next_data.get("instructions") or "").strip():
        next_data["instructions"] = (
            "1. Read prior pipeline outputs and the operator request.\n"
            "2. Decide the smallest safe diagnostic action.\n"
            "3. If server access is configured, inspect logs/status without destructive changes.\n"
            "4. If information is missing, state exactly what is missing.\n"
            "5. Return a short result, evidence, and next action."
        )
        _warn(warnings, f"AI node '{node_label}' was missing instructions; working instructions were added.")
    if not str(next_data.get("expected_output") or "").strip():
        next_data["expected_output"] = "Short operational summary with status, evidence, risks, and recommended next action."
    return next_data


def _append_ai_edge(
    edges: list[dict[str, Any]],
    seen_edges: set[tuple[str, str, str, str]],
    *,
    source: str,
    target: str,
    source_handle: str,
    target_handle: str = "",
    label: str | None = None,
    warnings: list[str] | None = None,
    reason: str | None = None,
) -> bool:
    if not source or not target or source == target:
        return False
    edge_key = (source, target, source_handle, target_handle)
    if edge_key in seen_edges:
        _warn(warnings, f"Duplicate AI edge '{source}->{target}' was dropped.")
        return False
    if _edge_path_exists(edges, start=target, goal=source):
        _warn(warnings, f"AI edge '{source}->{target}' would create a cycle and was dropped.")
        return False
    seen_edges.add(edge_key)
    edges.append(
        {
            "source": source,
            "target": target,
            "label": label,
            "source_handle": source_handle,
            "target_handle": target_handle or None,
        }
    )
    if reason:
        _warn(warnings, f"AI graph repair added edge '{source}->{target}' ({reason}).")
    return True


def _sanitize_graph_patch(
    raw_graph_patch: object,
    *,
    fallback_anchor: str | None = None,
    known_node_types: dict[str, str] | None = None,
    known_edges: list[dict[str, Any]] | None = None,
    task_hint: str = "",
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(raw_graph_patch, dict):
        return {
            "anchor_node_id": fallback_anchor,
            "nodes": [],
            "edges": [],
            "update_nodes": [],
            "remove_node_ids": [],
            "remove_edge_ids": [],
        }

    raw_nodes = raw_graph_patch.get("nodes")
    raw_edges = raw_graph_patch.get("edges")
    if not isinstance(raw_nodes, list):
        raw_nodes = []
    if not isinstance(raw_edges, list):
        raw_edges = []

    nodes: list[dict[str, Any]] = []
    dropped_refs: set[str] = set()
    new_node_types: dict[str, str] = {}
    inferred_edges: list[dict[str, Any]] = []
    for item in raw_nodes[:24]:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("ref") or item.get("id") or "").strip()
        if not ref:
            continue
        node_type = _canonical_node_type(item.get("type"), ref=ref, warnings=warnings)
        if node_type is None:
            dropped_refs.add(ref)
            edge = _edge_from_placeholder_node(item)
            if edge is not None:
                inferred_edges.append(edge)
            continue
        raw_data = item.get("data")
        label = str(item.get("label") or "").strip()
        data = raw_data if isinstance(raw_data, dict) else {}
        data = _ensure_ai_node_instructions(
            node_type=node_type,
            data=data,
            label=label or _humanize_ref(ref),
            task_hint=task_hint,
            warnings=warnings,
        )
        try:
            x_offset = float(item["x_offset"]) if item.get("x_offset") not in (None, "") else None
        except (TypeError, ValueError):
            x_offset = None
        try:
            y_offset = float(item["y_offset"]) if item.get("y_offset") not in (None, "") else None
        except (TypeError, ValueError):
            y_offset = None
        _append_ai_node(
            nodes,
            new_node_types,
            ref=ref,
            node_type=node_type,
            data=data,
            label=label or None,
            x_offset=x_offset,
            y_offset=y_offset,
        )

    edges: list[dict[str, Any]] = []
    source_type_lookup = {**(known_node_types or {}), **new_node_types}
    known_graph_refs = set(source_type_lookup)
    raw_remove_edge_ids = raw_graph_patch.get("remove_edge_ids")
    if not isinstance(raw_remove_edge_ids, list):
        raw_remove_edge_ids = []
    remove_edge_ids = [str(item).strip() for item in raw_remove_edge_ids[:48] if str(item).strip()]
    known_incoming_edges: dict[str, list[dict[str, Any]]] = {}
    for edge in known_edges or []:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        if source and target:
            known_incoming_edges.setdefault(target, []).append(edge)

    for item in [*raw_edges, *inferred_edges][:48]:
        if not isinstance(item, dict):
            continue
        for endpoint in ("source", "target"):
            raw_ref = str(item.get(endpoint) or "").strip()
            if not raw_ref or raw_ref in known_graph_refs or raw_ref in dropped_refs:
                continue
            if _resolve_graph_ref(raw_ref, known_graph_refs):
                continue
            inferred_type = _infer_structural_node_type(raw_ref)
            if not inferred_type:
                continue
            _append_ai_node(
                nodes,
                new_node_types,
                ref=raw_ref,
                node_type=inferred_type,
                label=_humanize_ref(raw_ref),
            )
            source_type_lookup[raw_ref] = inferred_type
            known_graph_refs.add(raw_ref)
            _warn(warnings, f"AI referenced missing structural node '{raw_ref}', created '{inferred_type}'.")

    seen_edges: set[tuple[str, str, str, str]] = set()
    for item in [*raw_edges, *inferred_edges][:48]:
        if not isinstance(item, dict):
            continue
        raw_source = str(item.get("source") or "").strip()
        raw_target = str(item.get("target") or "").strip()
        source = _resolve_graph_ref(raw_source, known_graph_refs) or raw_source
        target = _resolve_graph_ref(raw_target, known_graph_refs) or raw_target
        if not source or not target:
            continue
        if raw_source in dropped_refs or raw_target in dropped_refs or source in dropped_refs or target in dropped_refs:
            _warn(warnings, f"AI edge '{raw_source}->{raw_target}' referenced a dropped node and was dropped.")
            continue
        if source not in known_graph_refs or target not in known_graph_refs:
            _warn(warnings, f"AI edge '{raw_source}->{raw_target}' referenced a missing node and was dropped.")
            continue
        if source != raw_source or target != raw_target:
            _warn(warnings, f"AI edge '{raw_source}->{raw_target}' was rewired to '{source}->{target}'.")
        source_type = source_type_lookup.get(source, "")
        source_handle = _normalize_source_handle(
            item.get("source_handle"),
            source=source,
            source_type=source_type,
            warnings=warnings,
        )
        target_handle = str(item.get("target_handle") or "").strip() or ""
        _append_ai_edge(
            edges,
            seen_edges,
            source=source,
            target=target,
            source_handle=source_handle,
            target_handle=target_handle,
            label=str(item.get("label") or "").strip() or None,
            warnings=warnings,
        )

    def _add_repair_edge(source: str, target: str, reason: str) -> None:
        if not source or not target or source == target:
            return
        if source not in known_graph_refs or target not in known_graph_refs:
            return
        source_handle = _default_source_handle(source_type_lookup.get(source, ""))
        _append_ai_edge(
            edges,
            seen_edges,
            source=source,
            target=target,
            source_handle=source_handle,
            warnings=warnings,
            reason=reason,
        )

    anchor_node_id = str(raw_graph_patch.get("anchor_node_id") or "").strip() or fallback_anchor
    anchor_node_id = _resolve_graph_ref(anchor_node_id or "", known_graph_refs) or anchor_node_id
    if anchor_node_id not in known_graph_refs:
        anchor_node_id = None

    def _incoming_targets() -> set[str]:
        return {str(edge.get("target") or "") for edge in edges if str(edge.get("target") or "")}

    def _outgoing_sources() -> set[str]:
        return {str(edge.get("source") or "") for edge in edges if str(edge.get("source") or "")}

    # Auto-inject trigger/webhook if the combined graph (existing + new) has no trigger nodes.
    # This prevents the "Pipeline must include at least one trigger node" error for AI drafts
    # that forgot to add a trigger (common with Telegram bot patterns).
    existing_has_trigger = any(v.startswith("trigger/") for v in (known_node_types or {}).values())
    new_has_trigger = any(v.startswith("trigger/") for v in new_node_types.values())
    if not existing_has_trigger and not new_has_trigger and nodes:
        auto_trigger_ref = "auto_webhook_trigger"
        _append_ai_node(
            nodes,
            new_node_types,
            ref=auto_trigger_ref,
            node_type="trigger/webhook",
            label="Webhook / Telegram Trigger",
            data={"is_active": True},
            x_offset=0,
            y_offset=0,
        )
        source_type_lookup[auto_trigger_ref] = "trigger/webhook"
        known_graph_refs.add(auto_trigger_ref)
        _warn(
            warnings,
            "AI draft had no trigger node; a trigger/webhook was automatically added. "
            "Configure it with your Telegram webhook URL or replace with the appropriate trigger type.",
        )

    new_refs = [str(node.get("ref") or "") for node in nodes if str(node.get("ref") or "")]
    new_triggers = [ref for ref in new_refs if source_type_lookup.get(ref, "").startswith("trigger/")]
    incoming_targets = _incoming_targets()
    root_new_refs = [
        ref
        for ref in new_refs
        if ref not in incoming_targets and not source_type_lookup.get(ref, "").startswith("trigger/")
    ]

    if root_new_refs:
        start_ref = new_triggers[0] if new_triggers else anchor_node_id
        parallel_root = next((ref for ref in root_new_refs if source_type_lookup.get(ref) == "logic/parallel"), None)
        if start_ref and parallel_root:
            _add_repair_edge(start_ref, parallel_root, "connect new branch root")
            for ref in root_new_refs:
                if ref != parallel_root:
                    _add_repair_edge(parallel_root, ref, "connect parallel fan-out")
        elif start_ref:
            for ref in root_new_refs:
                _add_repair_edge(start_ref, ref, "connect unreachable new node")

    incoming_targets = _incoming_targets()
    outgoing_sources = _outgoing_sources()
    merge_refs = [ref for ref in new_refs if source_type_lookup.get(ref) == "logic/merge"]
    output_refs = [ref for ref in new_refs if source_type_lookup.get(ref, "").startswith("output/")]
    branch_leaf_refs = [
        ref
        for ref in new_refs
        if ref not in outgoing_sources
        and source_type_lookup.get(ref) not in {"logic/merge"}
        and not source_type_lookup.get(ref, "").startswith(("trigger/", "output/"))
    ]
    for merge_ref in merge_refs:
        existing_merge_sources = {
            str(edge.get("source") or "")
            for edge in edges
            if str(edge.get("target") or "") == merge_ref
        }
        for leaf_ref in branch_leaf_refs[:4]:
            if leaf_ref not in existing_merge_sources:
                _add_repair_edge(leaf_ref, merge_ref, "feed merge from new branch leaf")

    incoming_targets = _incoming_targets()
    outgoing_sources = _outgoing_sources()
    for output_ref in output_refs:
        if output_ref in incoming_targets:
            continue
        source_ref = next((ref for ref in merge_refs if ref in outgoing_sources or ref in incoming_targets), None)
        if not source_ref:
            source_ref = next((ref for ref in branch_leaf_refs if ref != output_ref), None)
        if source_ref:
            _add_repair_edge(source_ref, output_ref, "connect output from repaired branch")

    def _existing_edge_source_handle(edge: dict[str, Any]) -> str:
        source = str(edge.get("source") or "").strip()
        source_type = source_type_lookup.get(source, "")
        return _normalize_source_handle(
            edge.get("sourceHandle") or edge.get("source_handle"),
            source=source,
            source_type=source_type,
            warnings=warnings,
        )

    for target in list(known_graph_refs):
        target_type = source_type_lookup.get(target, "")
        if target_type == "logic/merge":
            continue
        existing_incoming = [
            edge
            for edge in known_incoming_edges.get(target, [])
            if str(edge.get("id") or "").strip() not in set(remove_edge_ids)
        ]
        new_incoming = [edge for edge in edges if str(edge.get("target") or "") == target]
        if not existing_incoming or not new_incoming:
            continue

        merge_ref_base = f"{target}_ai_merge"
        merge_ref = merge_ref_base
        counter = 2
        while merge_ref in known_graph_refs:
            merge_ref = f"{merge_ref_base}_{counter}"
            counter += 1
        _append_ai_node(
            nodes,
            new_node_types,
            ref=merge_ref,
            node_type="logic/merge",
            label=f"Merge before {_humanize_ref(target)}",
        )
        source_type_lookup[merge_ref] = "logic/merge"
        known_graph_refs.add(merge_ref)

        for edge in existing_incoming:
            edge_id = str(edge.get("id") or "").strip()
            source = str(edge.get("source") or "").strip()
            if edge_id:
                remove_edge_ids.append(edge_id)
            else:
                _warn(warnings, f"Existing edge '{source}->{target}' has no id and could not be removed cleanly.")
            if source in known_graph_refs:
                _append_ai_edge(
                    edges,
                    seen_edges,
                    source=source,
                    target=merge_ref,
                    source_handle=_existing_edge_source_handle(edge),
                    warnings=warnings,
                    reason="preserve existing branch before shared target",
                )

        for edge in new_incoming:
            edge["target"] = merge_ref
            edge["target_handle"] = None

        _add_repair_edge(merge_ref, target, "insert explicit merge before shared target")
        _warn(warnings, f"AI graph repair inserted merge '{merge_ref}' before '{target}' to avoid multiple incoming edges.")

    raw_update_nodes = raw_graph_patch.get("update_nodes")
    if not isinstance(raw_update_nodes, list):
        raw_update_nodes = []
    update_nodes: list[dict[str, Any]] = []
    for item in raw_update_nodes[:24]:
        if not isinstance(item, dict):
            continue
        node_id = str(item.get("node_id") or "").strip()
        raw_data = item.get("data")
        if not node_id or not isinstance(raw_data, dict):
            continue
        update_nodes.append({"node_id": node_id, "data": raw_data})

    raw_remove_node_ids = raw_graph_patch.get("remove_node_ids")
    if not isinstance(raw_remove_node_ids, list):
        raw_remove_node_ids = []
    remove_node_ids = [str(item).strip() for item in raw_remove_node_ids[:24] if str(item).strip()]

    return {
        "anchor_node_id": anchor_node_id,
        "nodes": nodes,
        "edges": edges,
        "update_nodes": update_nodes,
        "remove_node_ids": remove_node_ids,
        "remove_edge_ids": list(dict.fromkeys(remove_edge_ids)),
    }


async def _call_llm(*, user_prompt: str) -> str:
    provider = LLMProvider()
    chunks: list[str] = []
    async for chunk in provider.stream_chat(
        user_prompt,
        model="auto",
        purpose="chat",
        system_prompt=_SYSTEM_PROMPT,
        json_mode=True,
    ):
        chunks.append(chunk)
    return "".join(chunks)


def get_pipeline_assistant_context(
    *,
    pipeline_name: str,
    graph_overview: dict[str, Any],
    focus_node: dict[str, Any] | None,
    incoming_nodes: list[dict[str, Any]],
    outgoing_nodes: list[dict[str, Any]],
    graph_nodes: list[dict[str, Any]],
    available_agents: list[dict[str, Any]],
    available_servers: list[dict[str, Any]],
    available_mcp_servers: list[dict[str, Any]],
    selected_mcp_tools: list[dict[str, Any]],
    available_skills: list[dict[str, Any]],
    selected_skill_details: list[dict[str, Any]],
    intent: str = "edit",
    last_validation_errors: list[str] | None = None,
    last_run_summary: dict[str, Any] | None = None,
    draft_mode: bool = True,
) -> dict[str, Any]:
    return {
        "pipeline_name": pipeline_name,
        "intent": intent,
        "draft_mode": draft_mode,
        "node_catalog": _node_catalog_payload(),
        "graph_overview": graph_overview,
        "focus_node": focus_node,
        "incoming_nodes": incoming_nodes,
        "outgoing_nodes": outgoing_nodes,
        "graph_nodes": graph_nodes,
        "available_agents": available_agents,
        "available_servers": available_servers,
        "available_mcp_servers": available_mcp_servers,
        "selected_mcp_tools": selected_mcp_tools,
        "available_skills": available_skills,
        "selected_skill_details": selected_skill_details,
        "last_validation_errors": last_validation_errors or [],
        "last_run_summary": last_run_summary or {},
    }


def build_pipeline_assistant_response(
    *,
    user_message: str,
    conversation_history: list[dict[str, Any]],
    assistant_context: dict[str, Any],
    known_node_ids: set[str] | None = None,
    known_node_types: dict[str, str] | None = None,
    known_edges: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    safe_user_message = (
        sanitize_prompt_context_text(user_message).text.strip()[:4000]
        or "Запрос пользователя был отфильтрован как небезопасный prompt-контент."
    )
    user_prompt = f"""История диалога:
{_prompt_json(conversation_history, limit=12000)}

Контекст пайплайна:
{_prompt_json(assistant_context, limit=36000)}

Вопрос пользователя:
{safe_user_message}
"""

    loop = asyncio.new_event_loop()
    try:
        raw_response = loop.run_until_complete(_call_llm(user_prompt=user_prompt))
    except Exception as exc:
        raise PipelineAssistantError(f"LLM error: {exc}", 500) from exc
    finally:
        loop.close()

    parsed = _extract_json_object(raw_response)
    if not parsed:
        fallback_reply = sanitize_prompt_context_text(raw_response).text.strip() or "Ассистент вернул невалидный JSON-ответ."
        return {
            "reply": fallback_reply,
            "target_node_id": None,
            "node_patch": {},
            "graph_patch": _sanitize_graph_patch(None),
            "warnings": ["Ассистент вернул невалидный structured output."],
            "patch_summary": "",
            "suggested_next_actions": [],
        }

    reply = str(parsed.get("reply") or "").strip() or sanitize_prompt_context_text(raw_response).text.strip() or "No assistant response."
    target_node_id = str(parsed.get("target_node_id") or "").strip() or None
    node_patch = parsed.get("node_patch")
    if not isinstance(node_patch, dict):
        node_patch = {}

    warnings = parsed.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
    warning_items = [str(item) for item in warnings if str(item).strip()][:8]

    suggested_next_actions = parsed.get("suggested_next_actions")
    if not isinstance(suggested_next_actions, list):
        suggested_next_actions = []
    suggested_next_action_items = [str(item).strip() for item in suggested_next_actions if str(item).strip()][:8]

    known_ids = known_node_ids or set()
    if target_node_id and target_node_id not in known_ids:
        warning_items.append(f"Unknown target_node_id '{target_node_id}' ignored.")
        target_node_id = None
        node_patch = {}
    if not target_node_id:
        node_patch = {}

    graph_patch = _sanitize_graph_patch(
        parsed.get("graph_patch"),
        fallback_anchor=target_node_id,
        known_node_types=known_node_types,
        known_edges=known_edges,
        task_hint=safe_user_message,
        warnings=warning_items,
    )

    return {
        "reply": reply,
        "target_node_id": target_node_id,
        "node_patch": node_patch,
        "graph_patch": graph_patch,
        "warnings": warning_items[:8],
        "patch_summary": str(parsed.get("patch_summary") or "").strip(),
        "suggested_next_actions": suggested_next_action_items,
    }
