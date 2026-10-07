"""In-process authorization-code handoff for live AUTH_START runners."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, unquote_plus, urlparse

_AUTH_CODE = re.compile(r"^[A-Za-z0-9_./+=-]{8,2048}$")
_OAUTH_STATE = re.compile(r"^[A-Za-z0-9._~-]{1,128}$")
_queues: dict[str, asyncio.Queue[AuthInputMessage]] = {}


@dataclass(frozen=True, slots=True)
class AuthInputMessage:
    authorization_code: str
    oauth_state: str = ""


def register_auth_input_queue(invocation_id: str) -> asyncio.Queue[AuthInputMessage]:
    queue: asyncio.Queue[AuthInputMessage] = asyncio.Queue(maxsize=1)
    _queues[invocation_id] = queue
    return queue


def unregister_auth_input_queue(invocation_id: str) -> None:
    _queues.pop(invocation_id, None)


def extract_authorization_payload(raw: str) -> tuple[str, str]:
    """Return (authorization_code, oauth_state) from a bare code or callback URL/query."""
    text = unquote_plus(unquote((raw or "").strip())).strip()
    if not text:
        raise ValueError("authorization_code is empty")
    if "code=" in text:
        candidate = text
        if "://" not in candidate:
            candidate = "https://antigravity.google/oauth-callback?" + candidate.lstrip("?&")
        parsed = urlparse(candidate)
        query = parse_qs(parsed.query)
        code = unquote_plus(unquote((query.get("code") or [""])[0].strip())).strip()
        state = (query.get("state") or [""])[0].strip()
        if not code:
            raise ValueError("authorization_code missing from callback")
        if not _AUTH_CODE.fullmatch(code):
            raise ValueError("authorization_code has an invalid format")
        if state and not _OAUTH_STATE.fullmatch(state):
            raise ValueError("oauth_state has an invalid format")
        return code, state
    if not _AUTH_CODE.fullmatch(text):
        raise ValueError("authorization_code has an invalid format")
    return text, ""


def normalize_authorization_code(value: str) -> str:
    # Google sometimes shows/copy codes URL-encoded (%2F); also accept full callback URLs.
    code, _state = extract_authorization_payload(value)
    return code


def normalize_oauth_state(value: str) -> str:
    state = (value or "").strip()
    if not state:
        return ""
    if not _OAUTH_STATE.fullmatch(state):
        raise ValueError("oauth_state has an invalid format")
    return state


async def publish_auth_input(
    invocation_id: str,
    authorization_code: str,
    *,
    oauth_state: str = "",
) -> bool:
    queue = _queues.get(invocation_id)
    if queue is None:
        return False
    code, extracted_state = extract_authorization_payload(authorization_code)
    # Prefer state embedded in a pasted callback URL (detects stale-link paste).
    state = normalize_oauth_state(extracted_state or oauth_state)
    if queue.full():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    queue.put_nowait(AuthInputMessage(authorization_code=code, oauth_state=state))
    return True


async def wait_auth_input(invocation_id: str, *, timeout: float) -> AuthInputMessage | None:
    queue = _queues.get(invocation_id)
    if queue is None:
        return None
    try:
        return await asyncio.wait_for(queue.get(), timeout=timeout)
    except TimeoutError:
        return None


def clear_auth_input_queue(invocation_id: str) -> None:
    queue = _queues.get(invocation_id)
    if queue is None:
        return
    while True:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            return
