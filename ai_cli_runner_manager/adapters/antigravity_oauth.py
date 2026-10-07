"""Adapter-owned Google PKCE for Antigravity (bypasses the CLI's hard 60s paste wait).

Uses the same public desktop OAuth client embedded in the official Antigravity CLI
binary. Credentials are loaded from env or extracted from the local CLI binary at
runtime — they are not committed to source. This performs the user's own sign-in;
it does not import host credential files.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import time
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from ai_cli_runner_manager.auth_input import extract_authorization_payload as _extract_auth_payload

logger = logging.getLogger(__name__)

_OAUTH_REDIRECT_URI = "https://antigravity.google/oauth-callback"
_OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/auth"
_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
_OAUTH_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
_OAUTH_SCOPES = (
    "https://www.googleapis.com/auth/cloud-platform "
    "https://www.googleapis.com/auth/userinfo.email "
    "https://www.googleapis.com/auth/userinfo.profile "
    "https://www.googleapis.com/auth/cclog "
    "https://www.googleapis.com/auth/experimentsandconfigs "
    "https://www.googleapis.com/auth/aicode "
    "openid"
)
# Stable link window — independent of the CLI's 60s interactive wait.
_AUTH_LINK_TTL_SECONDS = 600
_CLIENT_ID_RE = re.compile(rb"([0-9]{6,}-[a-z0-9]+\.apps\.googleusercontent\.com)")
_CLIENT_SECRET_RE = re.compile(rb"(GOCSPX-[A-Za-z0-9_-]{10,})")


def auth_link_ttl_seconds() -> int:
    return _AUTH_LINK_TTL_SECONDS


def state_hash(state: str) -> str:
    return hashlib.sha256((state or "").encode("utf-8")).hexdigest()[:16]


def generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for S256 PKCE."""
    verifier = secrets.token_urlsafe(64)[:96]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def generate_oauth_state() -> str:
    # Fits AIConnectionAuthFlow.user_code (max 64) and OAuth state charset.
    return secrets.token_urlsafe(24)[:32]


@lru_cache(maxsize=1)
def oauth_client_credentials() -> tuple[str, str]:
    """Return (client_id, client_secret) for the Antigravity desktop OAuth client."""
    env_id = (os.getenv("ANTIGRAVITY_OAUTH_CLIENT_ID") or "").strip()
    env_secret = (os.getenv("ANTIGRAVITY_OAUTH_CLIENT_SECRET") or "").strip()
    if env_id and env_secret:
        return env_id, env_secret

    cli_path = shutil.which("antigravity") or shutil.which("agy")
    if not cli_path:
        raise RuntimeError("oauth_client_missing")
    try:
        blob = Path(cli_path).read_bytes()
    except OSError as exc:
        raise RuntimeError("oauth_client_unreadable") from exc

    ids = _CLIENT_ID_RE.findall(blob)
    secrets_found = _CLIENT_SECRET_RE.findall(blob)
    if not ids or not secrets_found:
        raise RuntimeError("oauth_client_not_in_binary")

    client_id = ids[0].decode("ascii")
    id_idx = blob.find(ids[0])
    best = secrets_found[0]
    best_dist = 10**12
    for secret in secrets_found:
        dist = abs(blob.find(secret) - id_idx)
        if dist < best_dist:
            best = secret
            best_dist = dist
    client_secret = best.decode("ascii")
    logger.info(
        "antigravity_oauth_client_loaded source=binary client_id_suffix=%s",
        client_id[-12:],
    )
    return client_id, client_secret


def build_authorization_url(*, state: str, code_challenge: str) -> str:
    client_id, _secret = oauth_client_credentials()
    query = urlencode(
        {
            "access_type": "offline",
            "client_id": client_id,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "prompt": "consent",
            "redirect_uri": _OAUTH_REDIRECT_URI,
            "response_type": "code",
            "scope": _OAUTH_SCOPES,
            "state": state,
        }
    )
    return f"{_OAUTH_AUTH_URL}?{query}"


def extract_authorization_payload(raw: str) -> tuple[str, str]:
    """Extract (authorization_code, oauth_state) from a bare code or callback URL/query."""
    return _extract_auth_payload(raw)


async def exchange_authorization_code(*, code: str, code_verifier: str) -> dict[str, Any]:
    client_id, client_secret = oauth_client_credentials()
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "code_verifier": code_verifier,
        "grant_type": "authorization_code",
        "redirect_uri": _OAUTH_REDIRECT_URI,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(_OAUTH_TOKEN_URL, data=data)
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("token_response_invalid") from exc
    if response.status_code != 200 or not isinstance(payload, dict):
        error = (
            str(payload.get("error") or f"http_{response.status_code}")
            if isinstance(payload, dict)
            else f"http_{response.status_code}"
        )
        description = str(payload.get("error_description") or "") if isinstance(payload, dict) else ""
        raise RuntimeError(f"token_exchange:{error}:{description}"[:240])
    if not payload.get("access_token") or not payload.get("refresh_token"):
        raise RuntimeError("token_exchange:missing_tokens")
    return payload


async def enrich_with_email(token_payload: dict[str, Any]) -> dict[str, Any]:
    access = str(token_payload.get("access_token") or "")
    if not access:
        return token_payload
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                _OAUTH_USERINFO_URL,
                headers={"Authorization": f"Bearer {access}"},
            )
        if response.status_code != 200:
            return token_payload
        info = response.json()
        if isinstance(info, dict) and info.get("email"):
            token_payload = {**token_payload, "email": str(info["email"])}
    except Exception:  # noqa: BLE001 - email enrichment is optional
        return token_payload
    return token_payload


def credential_document_from_token_payload(token_payload: dict[str, Any]) -> dict[str, Any]:
    expires_in = int(token_payload.get("expires_in") or 3600)
    expiry_date = int(time.time() * 1000) + max(60, expires_in) * 1000
    doc: dict[str, Any] = {
        "access_token": str(token_payload["access_token"]),
        "refresh_token": str(token_payload["refresh_token"]),
        "token_type": str(token_payload.get("token_type") or "Bearer"),
        "expiry_date": expiry_date,
        "scope": str(token_payload.get("scope") or _OAUTH_SCOPES),
    }
    if token_payload.get("id_token"):
        doc["id_token"] = str(token_payload["id_token"])
    if token_payload.get("email"):
        doc["email"] = str(token_payload["email"])
    return doc


def persist_oauth_credentials(creds_home: Path, document: dict[str, Any]) -> None:
    """Write CLI-compatible OAuth JSON under GEMINI_HOME (never log token values)."""
    gemini = creds_home / ".gemini"
    antigravity_cli = gemini / "antigravity-cli"
    gemini.mkdir(parents=True, exist_ok=True)
    antigravity_cli.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, ensure_ascii=False, indent=2)
    targets = [
        gemini / "oauth_creds.json",
        antigravity_cli / "oauth_creds.json",
        creds_home / "credentials.json",
    ]
    email = str(document.get("email") or "").strip()
    if email:
        safe = re.sub(r"[^A-Za-z0-9._@+-]", "_", email)[:120]
        targets.append(gemini / f"oauth_creds_{safe}.json")
    for path in targets:
        if path.name == "credentials.json":
            path.write_text(
                json.dumps(
                    {
                        "authenticated": True,
                        "access_token": document.get("access_token"),
                        "refresh_token": document.get("refresh_token"),
                        "token_type": document.get("token_type"),
                        "expiry_date": document.get("expiry_date"),
                        "scope": document.get("scope"),
                        "email": document.get("email"),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        else:
            path.write_text(payload, encoding="utf-8")
    logger.info(
        "antigravity_oauth_persisted paths=%s has_email=%s",
        len(targets),
        bool(email),
    )
