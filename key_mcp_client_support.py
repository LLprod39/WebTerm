"""Shared constants and helper primitives for the Keycloak MCP client."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from key_mcp_config import clean_text as _clean_text

DEFAULT_KEYCLOAK_URL = (os.getenv("KEYCLOAK_URL") or os.getenv("KEYCLOAK_HOST") or "").strip()
DEFAULT_REALM = os.getenv("KEYCLOAK_REALM", "").strip()
DEFAULT_TOKEN_REALM = os.getenv("KEYCLOAK_TOKEN_REALM", "").strip()
DEFAULT_CLIENT_ID = (os.getenv("KEYCLOAK_CLIENT_ID") or "admin-cli").strip() or "admin-cli"
DEFAULT_ADMIN_USER = os.getenv("KEYCLOAK_ADMIN_USER", "").strip()
DEFAULT_ADMIN_PASSWORD = os.getenv("KEYCLOAK_ADMIN_PASSWORD", "").strip()
DEFAULT_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "").strip()
DEFAULT_PROFILE = os.getenv("KEYCLOAK_DEFAULT_PROFILE", "").strip()
DEFAULT_VERIFY_SSL = os.getenv("KEYCLOAK_VERIFY_SSL", "true").strip().lower() == "true"
ALLOW_INSECURE_HTTP = os.getenv("KEYCLOAK_ALLOW_INSECURE_HTTP", "false").strip().lower() == "true"
MAX_RETRIES = max(1, int(os.getenv("KEYCLOAK_MAX_RETRIES", "3")))
RETRY_DELAY_SECONDS = max(0.1, float(os.getenv("KEYCLOAK_RETRY_DELAY", "1.5")))
REQUEST_TIMEOUT_SECONDS = max(5, int(os.getenv("KEYCLOAK_REQUEST_TIMEOUT", "30")))
MAX_SEARCH_RESULTS = max(1, int(os.getenv("KEYCLOAK_MAX_SEARCH_RESULTS", "50")))
DEFAULT_GROUP_PAGE_SIZE = max(10, int(os.getenv("KEYCLOAK_GROUP_PAGE_SIZE", "200")))
PROFILE_FILE = Path(os.getenv("KEYCLOAK_PROFILES_FILE", str(Path(__file__).resolve().parent / "config" / "keycloak_profiles.json")))
EMAIL_DOMAIN_CANDIDATES = [
    item.strip() for item in os.getenv("KEYCLOAK_EMAIL_DOMAINS", "erg.kz,corp.erg.kz,mail.erg.kz").split(",") if item.strip()
]
HTTP_PROXIES = {
    key: value
    for key, value in {
        "http": os.getenv("HTTP_PROXY") or os.getenv("http_proxy"),
        "https": os.getenv("HTTPS_PROXY") or os.getenv("https_proxy"),
    }.items()
    if value
}
LOGGER = logging.getLogger("keycloak-mcp")


class ToolError(RuntimeError):
    pass


def _looks_like_uuid(value: str) -> bool:
    raw = value.strip()
    return len(raw) == 36 and raw.count("-") == 4


def _dedupe_by_key(items: Iterable[dict[str, Any]], key: str = "id") -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        value = _clean_text(item.get(key))
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(item)
    return unique
