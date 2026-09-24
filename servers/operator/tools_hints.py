"""Message-intent parsing and host-hint helpers for operator tools (F-08a split).

Pure text processing over the operator's chat message — no Django/ORM. Used by
the operator loop (via the provider) and the inventory tools to decide between
showing the fleet inventory card and resolving a single named host.
"""

from __future__ import annotations

import re
from typing import Any

# User asked to *see* inventory in chat (interactive card).
# Includes typos like «Списко» via спис\w*
_INVENTORY_CARD_RE = re.compile(
    r"(?:"
    r"спис\w*\s+сервер|"  # список/списко/списки серверов
    r"сервер\w*.{0,24}спис\w*|"
    r"(?:покажи|выведи|вывести|дай|дай-ка)\s+(?:мне\s+)?(?:спис\w*\s+)?сервер|"
    r"какие\s+сервер|"
    r"все\s+сервер|"
    r"list\s+(?:all\s+)?servers?|"
    r"show\s+(?:me\s+)?(?:the\s+)?(?:server\s+)?list|"
    r"show\s+(?:me\s+)?(?:all\s+)?servers?|"
    r"inventory\b|"
    r"инвентар|"
    r"^серверы\s*[.!?…]?\s*$|"
    r"серверы\s*\?"
    r")",
    re.I | re.M,
)

# Connect / metrics / diagnose — must NOT open fleet inventory card.
_HOST_ACTION_RE = re.compile(
    r"(?:"
    r"подключ|"
    r"connect|"
    r"ssh\b|"
    r"метрик|"
    r"metrics?|"
    r"диагност|"
    r"diagnos|"
    r"\bdf\b|"
    r"docker|"
    r"uptime|"
    r"проверь|"
    r"check\b|"
    r"соберите?|"
    r"collect|"
    r"run\s+command|"
    r"выполни"
    r")",
    re.I,
)

# Update / deploy / checkout a Git branch on a host — prefer agent.create+run over catalog browsing.
_DEPLOY_OR_UPDATE_RE = re.compile(
    r"(?:"
    r"обнов|"
    r"update\b|"
    r"upgrad|"
    r"депло|"
    r"deploy|"
    r"roll\s*out|"
    r"rollout|"
    r"github\.com|"
    r"gitlab\.|"
    r"bitbucket\.|"
    r"git@|"
    r"ветк|"
    r"branch\b|"
    r"верси[яию]|"
    r"на\s+эту\s+верси|"
    r"frontend-v\d|"
    r"репозитор|"
    r"из\s+git|"
    r"git\s+pull|"
    r"checkout\b"
    r")",
    re.I,
)

DEPLOY_ACTION_NUDGE = (
    "Пользователь просит обновить/задеплоить на сервер. "
    "Пустой или нерелевантный каталог playbook/агентов — НЕ финальный ответ. "
    "Сейчас вызови agent.create (mode=full; name на русском; goal и system_prompt с URL/веткой "
    "из запроса; server_ids с уже найденного хоста), затем сразу agent.run. "
    "Confirm-кнопки появятся сами. Не спрашивай URL повторно, если он уже в сообщении."
)

_HOST_HINT_RE = re.compile(
    r"(?:"
    r"@([\w.-]{2,64})"
    r"|(?:сервер(?:у|а|е|ом)?|server|host)\s+([^\s,;:]+)"
    r"|(?:подключись|подключить|connect(?:\s+to)?)\s+(?:к\s+|to\s+)?(?:сервер(?:у)?\s+)?([^\s,;:]+)"
    r"|(?:метрик\w*|metrics?|прогноз\w*|forecasts?)\s+(?:сервер\w*\s+)?([^\s,;:]+)"
    r"|(?:на|к)\s+(?:сервер(?:е|у)?\s+)?([a-zA-Z0-9_.-]{2,64})"
    r")",
    re.I,
)

# Spoken / Cyrillic nicknames → inventory name stems
_HOST_ALIASES: dict[str, str] = {
    "графана": "grafana",
    "графаны": "grafana",
    "графану": "grafana",
    "графаной": "grafana",
    "grafana": "grafana",
    "луникс": "lunix",
    "lunix": "lunix",
    "прометей": "prom",
    "prometheus": "prom",
    "пром": "prom",
    "prom": "prom",
    "редис": "redis",
    "redis": "redis",
    "бастион": "bastion",
    "bastion": "bastion",
    "никитавм": "nikitavm",
    "никита": "nikita",
}

# Basic Russian phonetic transliteration for host matching (никитавм ↔ nikitavm).
_CYR_TO_LAT: dict[str, str] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def transliterate_cyrillic(text: str) -> str:
    """Map Cyrillic letters to a simple Latin form for inventory name matching."""
    out: list[str] = []
    for ch in str(text or "").lower():
        if ch in _CYR_TO_LAT:
            out.append(_CYR_TO_LAT[ch])
        else:
            out.append(ch)
    return "".join(out)


def user_wants_inventory_card(user_message: str | None) -> bool:
    """True only when the operator asked to list inventory in the chat UI."""
    text = str(user_message or "").strip()
    if not text:
        return False
    # Named-host actions never get a fleet card (even if the word «сервер» appears).
    if _HOST_ACTION_RE.search(text) and not _INVENTORY_CARD_RE.search(text):
        return False
    if _INVENTORY_CARD_RE.search(text):
        return True
    # Short phrases: «серверы», «servers please»
    compact = re.sub(r"\s+", " ", text.lower()).strip()
    if len(compact) <= 56 and re.search(r"сервер|servers?", compact):
        if re.search(r"спис|list|show|покаж|какие|все|инвентар|inventory", compact):
            return True
        if compact in {"серверы", "servers", "сервера", "server list"}:
            return True
    return False


def user_wants_named_host_action(user_message: str | None) -> bool:
    """Connect / metrics / diagnose on a host — never fleet list card."""
    text = str(user_message or "").strip()
    if not text:
        return False
    if user_wants_inventory_card(text):
        return False
    return bool(_HOST_ACTION_RE.search(text))


def user_wants_deploy_or_update(user_message: str | None) -> bool:
    """True when the operator asked to update/deploy/checkout a version or Git branch."""
    text = str(user_message or "").strip()
    if not text:
        return False
    return bool(_DEPLOY_OR_UPDATE_RE.search(text))


def normalize_host_hint(token: str | None) -> str:
    """Map «графаны» → grafana, «никитавм» → nikitavm, trim junk."""
    raw = str(token or "").strip().strip("«»\"'.,);:")
    if not raw:
        return ""
    low = raw.lower()
    if low in _HOST_ALIASES:
        return _HOST_ALIASES[low]
    # Stem common Russian endings
    for suf in ("ами", "ов", "ам", "ах", "ы", "и", "у", "е", "а", "ой", "ей"):
        if len(low) > 4 and low.endswith(suf):
            stem = low[: -len(suf)]
            if stem in _HOST_ALIASES:
                return _HOST_ALIASES[stem]
            if stem + "а" in _HOST_ALIASES:
                return _HOST_ALIASES[stem + "а"]
    # Cyrillic → Latin so «никитавм» matches inventory name nikitavm
    if any(("а" <= ch <= "я") or ch == "ё" for ch in low):
        latin = transliterate_cyrillic(low)
        if latin and latin != low:
            if latin in _HOST_ALIASES:
                return _HOST_ALIASES[latin]
            return latin
    return raw


def extract_server_hint(user_message: str | None) -> str | None:
    """Best-effort host token from natural language (графана, lunix, @web-prod-01)."""
    text = str(user_message or "").strip()
    if not text:
        return None
    m = _HOST_HINT_RE.search(text)
    if m:
        for g in m.groups():
            if g:
                token = g.strip().strip("«»\"'.,)@")
                if token.startswith("@"):
                    token = token[1:]
                if token and token.lower() not in {"сервер", "server", "host", "к", "to", "the", "и"}:
                    return normalize_host_hint(token) or token
    # Fallback: known aliases mentioned as whole words
    low = text.lower()
    for alias, canon in _HOST_ALIASES.items():
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", low):
            return canon
    return None


def prepare_list_servers_arguments(
    arguments: dict[str, Any] | None,
    *,
    user_message: str | None,
) -> dict[str, Any]:
    """UI policy for list_servers.

    - Explicit list request → show_in_chat, no filter (full inventory card).
    - Never auto-inject q from the user message into list_servers (that caused
      «графаны» to stick forever and empty name lists). Host lookup is resolve_server.
    """
    args = dict(arguments or {})
    if user_wants_inventory_card(user_message):
        args["show_in_chat"] = True
        for key in ("q", "name", "query"):
            args.pop(key, None)
        return args

    args["show_in_chat"] = False
    # Normalize model-supplied filter only — do not invent one from chat text.
    raw_q = str(args.get("q") or args.get("name") or args.get("query") or "").strip()
    if raw_q:
        args["q"] = normalize_host_hint(raw_q) or raw_q
        args.pop("name", None)
        args.pop("query", None)
    return args


def prefer_resolve_server_for_message(
    arguments: dict[str, Any] | None,
    *,
    user_message: str | None,
) -> dict[str, Any] | None:
    """If the user asked metrics/connect on a named host, return resolve_server args.

    Returns None when list_servers should still run (true inventory list).
    """
    if user_wants_inventory_card(user_message):
        return None
    if not user_wants_named_host_action(user_message):
        return None
    args = arguments if isinstance(arguments, dict) else {}
    model_q = str(args.get("q") or args.get("name") or args.get("query") or "").strip()
    hint = extract_server_hint(user_message)
    q = normalize_host_hint(model_q) or hint
    if not q:
        return None
    return {"q": q}


def server_matches_query(server, q: str) -> bool:
    """Loose name/host match: grafana ↔ grafana-01, графаны → grafana, никитавм → nikitavm."""
    q_raw = (q or "").strip()
    if not q_raw:
        return True
    q_norm = normalize_host_hint(q_raw).lower()
    q_low = q_raw.lower()
    q_latin = transliterate_cyrillic(q_low)
    name = (getattr(server, "name", None) or "").lower()
    host = (getattr(server, "host", None) or "").lower()
    tags = str(getattr(server, "tags", "") or "").lower()
    if str(getattr(server, "id", "")) == q_low:
        return True
    for token in {q_low, q_norm, q_latin}:
        if not token:
            continue
        if token in name or token in host or token in tags:
            return True
        if (
            name
            and (name.startswith(token) or token.startswith(name.split("-")[0]))
            and (name.startswith(token) or token in name.replace("-", ""))
        ):
            return True
        # stem match: grafana vs grafana-01
        name_stem = name.split("-")[0] if name else ""
        if (
            name_stem
            and (name_stem == token or token.startswith(name_stem) or name_stem.startswith(token))
            and len(token) >= 3
            and len(name_stem) >= 3
        ):
            return True
    return False
