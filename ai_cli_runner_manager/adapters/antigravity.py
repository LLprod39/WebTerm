"""Gemini Antigravity subscription adapter using the official Google Antigravity CLI and SDK."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import json
import os
import re
import secrets
import shutil
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from urllib.parse import parse_qs, urlparse

from ai_cli_runner_manager.auth_input import (
    clear_auth_input_queue,
    wait_auth_input,
)
from ai_cli_runner_manager.protocol import RunnerAction, RunnerRequestV1, error_event
from app.ai_runtime import ProviderEventType, ProviderEventV1

from . import antigravity_oauth
from .common import prompt_from_request, tool_response_events

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-3.8-flash"
_CREDENTIALS_DIR = Path("/credentials/antigravity")
# Official CLI prints a full Google OAuth consent URL (often >500 chars with scopes).
_GOOGLE_OAUTH_URL = re.compile(r"https://accounts\.google\.com/o/oauth2/auth\?[^\s\x1b\"'<>]+", re.IGNORECASE)
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\x1b.")
_OAUTH2_ERROR_RE = re.compile(r'oauth2:\s*"([a-z0-9_/-]+)"\s*"([^"]*)"', re.IGNORECASE)


class AntigravitySubscriptionAdapter:
    async def stream(self, request: RunnerRequestV1) -> AsyncGenerator[ProviderEventV1, None]:
        if request.action is RunnerAction.AUTH_START:
            async for event in _start_device_auth(
                api_key=getattr(request, "api_key", None),
                invocation_id=request.invocation_id,
            ):
                yield event
            return

        if request.action in {RunnerAction.AUTH_STATUS, RunnerAction.VERIFY}:
            authenticated = _is_authenticated()
            if authenticated:
                yield ProviderEventV1(ProviderEventType.COMPLETED, {"authenticated": True})
            else:
                yield ProviderEventV1(ProviderEventType.AUTH_REQUIRED, {"authenticated": False})
            return

        cli_path = shutil.which("antigravity") or shutil.which("agy")
        creds = _resolve_credentials()
        api_key = (
            getattr(request, "api_key", None)
            or creds.get("api_key")
            or os.getenv("GEMINI_API_KEY")
        )

        # Prefer official Antigravity CLI when available and no explicit API key.
        if cli_path and not api_key:
            try:
                async for event in _run_antigravity_cli(request):
                    yield event
                return
            except Exception as exc:  # noqa: BLE001
                yield _safe_antigravity_error(exc)
                return

        try:
            from google.antigravity import Agent, CapabilitiesConfig, LocalAgentConfig
        except ImportError:
            if cli_path:
                try:
                    async for event in _run_antigravity_cli(request):
                        yield event
                    return
                except Exception as exc:  # noqa: BLE001
                    yield _safe_antigravity_error(exc)
                    return
            yield error_event("provider_runtime_missing", "Google Antigravity SDK is not installed")
            return

        try:
            if not api_key:
                yield error_event(
                    "gemini_api_key_missing",
                    "Gemini API key is required. Please set GEMINI_API_KEY in .env or configure in Settings.",
                )
                return

            if api_key and not creds.get("api_key"):
                _persist_api_key(api_key)

            model = request.model_id or _DEFAULT_MODEL
            config = LocalAgentConfig(
                api_key=api_key,
                model=model,
                system_instructions=request.system_prompt,
                capabilities=CapabilitiesConfig(),
            )
            prompt = prompt_from_request(request)
            session_id = request.provider_session_id or f"session-{secrets.token_hex(8)}"

            async with Agent(config=config) as agent:
                response = await agent.chat(prompt)

                if hasattr(response, "thoughts"):
                    async for thought in response.thoughts:
                        if thought:
                            yield ProviderEventV1(
                                ProviderEventType.REASONING_DELTA,
                                {"text": str(thought)},
                            )

                buffered_text: list[str] = []
                async for token in response:
                    text_chunk = str(token)
                    if request.tools:
                        buffered_text.append(text_chunk)
                    else:
                        yield ProviderEventV1(
                            ProviderEventType.TEXT_DELTA,
                            {"text": text_chunk},
                        )

                if request.tools:
                    raw_text = "".join(buffered_text)
                    tool_events = tool_response_events(raw_text, request)
                    for event in tool_events:
                        yield event
                    if any(event.type is ProviderEventType.ERROR for event in tool_events):
                        return

                usage_payload: dict[str, int] = {}
                if hasattr(response, "usage") and isinstance(response.usage, dict):
                    usage_payload = response.usage
                elif hasattr(response, "token_count") and isinstance(response.token_count, int):
                    usage_payload = {"total_tokens": response.token_count}

                if usage_payload:
                    yield ProviderEventV1(ProviderEventType.USAGE, usage_payload)

                yield ProviderEventV1(
                    ProviderEventType.COMPLETED,
                    {"provider_session_id": session_id},
                )
        except Exception as exc:  # noqa: BLE001
            yield _safe_antigravity_error(exc)


_CLI_RUN_TIMEOUT_SECONDS = 90.0
_AUTH_PROMPT_MARKERS = (
    "authentication required",
    "please sign in",
    "please visit the url to log in",
    "waiting for authentication",
    "paste the authorization code",
    "not logged into antigravity",
)


def _stderr_requests_auth(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _AUTH_PROMPT_MARKERS)


async def _run_antigravity_cli(request: RunnerRequestV1) -> AsyncGenerator[ProviderEventV1, None]:
    cli_path = shutil.which("antigravity") or shutil.which("agy")
    if not cli_path:
        yield error_event("provider_runtime_missing", "Google Antigravity CLI binary is not available")
        return

    prompt = prompt_from_request(request)
    session_id = request.provider_session_id or f"session-{secrets.token_hex(8)}"
    cmd = [
        cli_path,
        "-p",
        prompt,
        "--dangerously-skip-permissions",
    ]
    if request.model_id:
        cmd.extend(["--model", request.model_id])
    if request.reasoning_effort:
        cmd.extend(["--effort", request.reasoning_effort])

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_cli_env(),
    )
    assert process.stdout is not None and process.stderr is not None

    buffered_text: list[str] = []
    stderr_chunks: list[str] = []
    auth_detected = asyncio.Event()
    text_queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def _pump_stdout() -> None:
        assert process.stdout is not None
        try:
            while chunk := await process.stdout.read(4096):
                text_chunk = chunk.decode("utf-8", errors="replace")
                if request.tools:
                    buffered_text.append(text_chunk)
                else:
                    await text_queue.put(text_chunk)
        finally:
            await text_queue.put(None)

    async def _pump_stderr() -> None:
        assert process.stderr is not None
        while chunk := await process.stderr.read(4096):
            text_chunk = chunk.decode("utf-8", errors="replace")
            stderr_chunks.append(text_chunk)
            if _stderr_requests_auth("".join(stderr_chunks)):
                auth_detected.set()
                return

    stdout_task = asyncio.create_task(_pump_stdout())
    stderr_task = asyncio.create_task(_pump_stderr())
    wait_task = asyncio.create_task(process.wait())
    auth_wait_task = asyncio.create_task(auth_detected.wait())
    timed_out = False
    try:
        # Stream plain-text tokens while waiting; tools path buffers until exit.
        while not request.tools:
            if auth_detected.is_set() or wait_task.done():
                break
            try:
                item = await asyncio.wait_for(text_queue.get(), timeout=0.2)
            except TimeoutError:
                continue
            if item is None:
                break
            if item:
                yield ProviderEventV1(ProviderEventType.TEXT_DELTA, {"text": item})

        done, not_done = await asyncio.wait(
            {wait_task, auth_wait_task},
            timeout=_CLI_RUN_TIMEOUT_SECONDS,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not done:
            timed_out = True
        # Never cancel wait_task here — we still need process.wait() after kill.
        if auth_wait_task in not_done:
            auth_wait_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await auth_wait_task
        if (auth_detected.is_set() or timed_out) and process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(wait_task, timeout=5)
    finally:
        for task in (stdout_task, stderr_task, wait_task, auth_wait_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(stdout_task, stderr_task, wait_task, auth_wait_task, return_exceptions=True)

    # Drain any remaining plaintext tokens after process exit.
    if not request.tools:
        while True:
            try:
                item = text_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item is None:
                break
            if item:
                yield ProviderEventV1(ProviderEventType.TEXT_DELTA, {"text": item})

    err_msg = "".join(stderr_chunks).strip()
    if auth_detected.is_set() or _stderr_requests_auth(err_msg):
        yield ProviderEventV1(ProviderEventType.AUTH_REQUIRED, {"authenticated": False})
        return
    if timed_out:
        yield error_event(
            "provider_timeout",
            f"Antigravity CLI timed out after {int(_CLI_RUN_TIMEOUT_SECONDS)}s",
            retryable=True,
        )
        return

    return_code = process.returncode if process.returncode is not None else 1
    if return_code != 0:
        yield error_event(
            "provider_runtime_error",
            f"Antigravity CLI exited with code {return_code}: {err_msg[:200]}",
        )
        return

    if request.tools:
        raw_text = "".join(buffered_text)
        tool_events = tool_response_events(raw_text, request)
        for event in tool_events:
            yield event
        if any(event.type is ProviderEventType.ERROR for event in tool_events):
            return

    yield ProviderEventV1(
        ProviderEventType.COMPLETED,
        {"provider_session_id": session_id},
    )


async def _start_device_auth(
    api_key: str | None = None,
    *,
    invocation_id: str = "",
) -> AsyncGenerator[ProviderEventV1, None]:
    """Adapter-owned Google PKCE (≥5 min stable link); writes CLI-shaped creds to GEMINI_HOME."""
    if api_key:
        _persist_api_key(api_key)
        yield ProviderEventV1(ProviderEventType.COMPLETED, {"authenticated": True})
        return

    try:
        antigravity_oauth.oauth_client_credentials()
    except RuntimeError:
        yield error_event(
            "provider_auth_failed",
            "Antigravity OAuth client is unavailable in this runner image",
        )
        return

    oauth_state = antigravity_oauth.generate_oauth_state()
    code_verifier, code_challenge = antigravity_oauth.generate_pkce_pair()
    verification_uri = antigravity_oauth.build_authorization_url(
        state=oauth_state,
        code_challenge=code_challenge,
    )
    link_ttl = antigravity_oauth.auth_link_ttl_seconds()
    logger.info(
        "antigravity_oauth_start state_hash=%s link_ttl=%s invocation_id=%s",
        antigravity_oauth.state_hash(oauth_state),
        link_ttl,
        invocation_id or "-",
    )
    yield ProviderEventV1(
        ProviderEventType.AUTH_REQUIRED,
        {
            "verification_uri": verification_uri,
            "user_code": oauth_state,
            "oauth_state": oauth_state,
            "expires_in": link_ttl,
            "accepts_authorization_code": True,
            "state_hash": antigravity_oauth.state_hash(oauth_state),
        },
    )

    if not invocation_id:
        # Unit-test / dry-run path: surface the stable link without waiting for a code.
        return

    clear_auth_input_queue(invocation_id)
    message = await wait_auth_input(invocation_id, timeout=float(link_ttl))
    if message is None:
        yield error_event(
            "provider_auth_timeout",
            "Google Antigravity sign-in timed out waiting for authorization code",
            retryable=True,
        )
        return

    try:
        code, pasted_state = antigravity_oauth.extract_authorization_payload(message.authorization_code)
    except ValueError:
        # publish_auth_input already normalized; fall back to the delivered code.
        code = message.authorization_code
        pasted_state = ""

    effective_state = pasted_state or message.oauth_state
    if effective_state and effective_state != oauth_state:
        logger.warning(
            "antigravity_oauth_state_mismatch session_hash=%s pasted_hash=%s",
            antigravity_oauth.state_hash(oauth_state),
            antigravity_oauth.state_hash(effective_state),
        )
        yield error_event(
            "provider_auth_session_mismatch",
            "Authorization code belongs to a previous sign-in link; open the current link and paste a fresh code",
        )
        return

    logger.info(
        "antigravity_oauth_code_received state_hash=%s code_len=%s",
        antigravity_oauth.state_hash(oauth_state),
        len(code),
    )
    try:
        token_payload = await antigravity_oauth.exchange_authorization_code(
            code=code,
            code_verifier=code_verifier,
        )
        token_payload = await antigravity_oauth.enrich_with_email(token_payload)
        document = antigravity_oauth.credential_document_from_token_payload(token_payload)
        creds_home = Path(os.getenv("GEMINI_HOME", str(_CREDENTIALS_DIR)))
        antigravity_oauth.persist_oauth_credentials(creds_home, document)
    except RuntimeError as exc:
        detail_text = str(exc)
        oauth_error = ""
        if detail_text.startswith("token_exchange:"):
            parts = detail_text.split(":", 2)
            oauth_error = parts[1] if len(parts) > 1 else ""
        event = error_event(
            "provider_auth_failed",
            "Google rejected the authorization code; open the current sign-in link and paste a fresh code once",
        )
        payload = {**event.payload}
        if oauth_error:
            payload["oauth_error"] = oauth_error[:80]
        if "invalid_grant" in detail_text:
            payload["oauth_error"] = payload.get("oauth_error") or "invalid_grant"
            event = error_event(
                "provider_auth_failed",
                "Google rejected the authorization code (invalid_grant). Open the current link and paste a fresh code once",
            )
            payload = {**event.payload, **{k: v for k, v in payload.items() if k.startswith("oauth_")}}
        yield ProviderEventV1(event.type, payload)
        return
    except OSError:
        yield error_event("provider_auth_failed", "Failed to persist Antigravity OAuth credentials")
        return

    if not _is_authenticated():
        yield error_event("provider_auth_failed", "Antigravity credentials were written but not detected")
        return
    yield ProviderEventV1(ProviderEventType.COMPLETED, {"authenticated": True})


def parse_antigravity_oauth_url(text: str, *, verification_uri: str = "") -> str:
    plain = _ANSI_RE.sub("", text)
    match = _GOOGLE_OAUTH_URL.search(plain)
    if not match:
        return verification_uri
    return match.group(0).rstrip(".,);]'\"")


def parse_antigravity_oauth_state(verification_uri: str) -> str:
    try:
        query = parse_qs(urlparse(verification_uri).query)
    except ValueError:
        return ""
    values = query.get("state") or []
    if not values:
        return ""
    state = str(values[0]).strip()
    return state[:64]


def _auth_failure_from_output(output: str) -> tuple[str, str, dict[str, str]]:
    plain = _ANSI_RE.sub("", output or "")
    lowered = plain.lower()
    detail: dict[str, str] = {}
    match = _OAUTH2_ERROR_RE.search(plain)
    if match:
        detail["oauth_error"] = match.group(1)[:80]
        description = (match.group(2) or "").strip()
        if description:
            detail["oauth_error_description"] = description[:160]
    # Prefer concrete OAuth error codes from the token endpoint over generic transport text.
    if detail.get("oauth_error") == "invalid_grant" or "invalid_grant" in lowered:
        return (
            "provider_auth_failed",
            "Google rejected the authorization code (invalid_grant). Open the current link and paste a fresh code once",
            detail,
        )
    # Only match oauth2:"invalid_request" — the consent URL itself always contains redirect_uri=.
    if detail.get("oauth_error") == "invalid_request":
        return (
            "provider_auth_failed",
            "Google rejected the authorization request; open the current sign-in link and try again",
            detail,
        )
    if "token exchange failed" in lowered and "dial tcp" in lowered:
        return (
            "provider_auth_transport_failed",
            "Google token exchange failed; check AI CLI egress and try sign-in again",
            detail,
        )
    if "token exchange failed" in lowered:
        return (
            "provider_auth_failed",
            "Google token exchange rejected the authorization code; open the current link and paste a fresh code once",
            detail,
        )
    # Match the CLI hard timeout, not the prompt "Waiting for authentication (timeout 60s)..."
    if "authentication timed out" in lowered:
        return (
            "provider_auth_timeout",
            "Google Antigravity sign-in link expired; open the new link and paste a fresh code",
            detail,
        )
    return (
        "provider_auth_failed",
        "Google Antigravity rejected the authorization code; open the latest link and paste a fresh code once",
        detail,
    )


def _cli_env() -> dict[str, str]:
    home = str(Path(os.getenv("GEMINI_HOME", str(_CREDENTIALS_DIR))))
    env = {**os.environ, "HOME": home, "GEMINI_HOME": home, "TERM": os.environ.get("TERM") or "xterm-256color"}
    return env


def _persist_api_key(api_key: str) -> None:
    creds_dir = Path(os.getenv("GEMINI_HOME", str(_CREDENTIALS_DIR)))
    try:
        creds_dir.mkdir(parents=True, exist_ok=True)
        (creds_dir / "api_key.txt").write_text(api_key, encoding="utf-8")
        json_file = creds_dir / "credentials.json"
        payload: dict[str, Any] = {}
        if json_file.exists():
            try:
                loaded = json.loads(json_file.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    payload = loaded
            except (json.JSONDecodeError, OSError):
                payload = {}
        payload["api_key"] = api_key
        payload["authenticated"] = True
        json_file.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass


def _is_authenticated() -> bool:
    creds = _resolve_credentials()
    if creds.get("api_key") or creds.get("access_token") or creds.get("refresh_token") or creds.get("client_id"):
        return True
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return True
    creds_dir = Path(os.getenv("GEMINI_HOME", str(_CREDENTIALS_DIR)))
    for relative in (
        Path("api_key.txt"),
        Path("token.json"),
        Path("credentials.json"),
        Path(".gemini") / "oauth_creds.json",
        Path(".gemini") / "antigravity-cli" / "oauth_creds.json",
    ):
        candidate = creds_dir / relative
        if not candidate.is_file():
            continue
        if candidate.name == "api_key.txt":
            if candidate.read_text(encoding="utf-8").strip():
                return True
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict) and (
            data.get("api_key")
            or data.get("access_token")
            or data.get("refresh_token")
            or data.get("token")
        ):
            return True
    return False


def _resolve_credentials() -> dict[str, Any]:
    creds_dir = Path(os.getenv("GEMINI_HOME", str(_CREDENTIALS_DIR)))
    if not creds_dir.exists():
        return {}

    key_file = creds_dir / "api_key.txt"
    if key_file.exists():
        key = key_file.read_text(encoding="utf-8").strip()
        if key:
            return {"api_key": key}

    for name in ("credentials.json", "token.json"):
        json_file = creds_dir / name
        if not json_file.exists():
            continue
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _safe_antigravity_error(exc: Exception) -> ProviderEventV1:
    value = str(exc).lower()
    if any(
        marker in value
        for marker in (
            "401",
            "unauthorized",
            "api_key_invalid",
            "permission denied",
            "login required",
            "api key not valid",
            "api key is required",
            "not logged into antigravity",
        )
    ):
        return ProviderEventV1(ProviderEventType.AUTH_REQUIRED, {"authenticated": False})
    if any(marker in value for marker in ("429", "rate limit", "resource exhausted", "quota exceeded")):
        return ProviderEventV1(ProviderEventType.LIMIT, {"code": "provider_limit_reached"})
    return error_event("provider_runtime_error", "Google Antigravity runtime failed")


