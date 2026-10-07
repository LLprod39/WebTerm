"""Gemini Antigravity subscription adapter using the official Google Antigravity CLI and SDK."""

from __future__ import annotations

import asyncio
import json
import os
import pty
import re
import secrets
import shutil
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from urllib.parse import parse_qs, urlparse

from ai_cli_runner_manager.auth_input import (
    AuthInputMessage,
    clear_auth_input_queue,
    wait_auth_input,
)
from ai_cli_runner_manager.protocol import RunnerAction, RunnerRequestV1, error_event
from app.ai_runtime import ProviderEventType, ProviderEventV1

from .common import prompt_from_request, tool_response_events

_DEFAULT_MODEL = "gemini-3.8-flash"
_CREDENTIALS_DIR = Path("/credentials/antigravity")
# Official CLI prints a full Google OAuth consent URL (often >500 chars with scopes).
_GOOGLE_OAUTH_URL = re.compile(r"https://accounts\.google\.com/o/oauth2/auth\?[^\s\x1b\"'<>]+", re.IGNORECASE)
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\x1b.")
_AUTH_URL_WAIT_SECONDS = 45.0
# Official CLI OAuth waits ~60s for a pasted code (hard limit). We keep that single
# PKCE process alive until it exits, then rotate the link inside this envelope.
_AUTH_TOTAL_WAIT_SECONDS = 600.0
_AUTH_LINK_TTL_SECONDS = 55
_AUTH_CODE_DRAIN_SECONDS = 45.0
_PTY_READ_CHUNK = 8192
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
    while chunk := await process.stdout.read(4096):
        text_chunk = chunk.decode("utf-8", errors="replace")
        if request.tools:
            buffered_text.append(text_chunk)
        else:
            yield ProviderEventV1(ProviderEventType.TEXT_DELTA, {"text": text_chunk})

    return_code = await process.wait()
    if return_code != 0:
        err_bytes = await process.stderr.read()
        err_msg = err_bytes.decode("utf-8", errors="replace").strip()
        if "authentication required" in err_msg.lower() or "please sign in" in err_msg.lower():
            yield ProviderEventV1(ProviderEventType.AUTH_REQUIRED, {"authenticated": False})
            return
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
    """Start Google Antigravity OAuth via CLI (pseudo-TTY); no dedicated login subcommand exists."""
    if api_key:
        _persist_api_key(api_key)
        yield ProviderEventV1(ProviderEventType.COMPLETED, {"authenticated": True})
        return

    cli_path = shutil.which("antigravity") or shutil.which("agy")
    if not cli_path or not os.path.exists(cli_path):
        # Host unit tests / images without the official binary.
        code = f"GEMI-{secrets.token_hex(3).upper()}-{secrets.token_hex(3).upper()}"
        yield ProviderEventV1(
            ProviderEventType.AUTH_REQUIRED,
            {
                "verification_uri": "https://accounts.google.com/o/oauth2/device/usercode",
                "user_code": code,
                "login_id": secrets.token_hex(16),
            },
        )
        return

    # Keep each CLI/PKCE process until it exits (~60s). Rotate only after that so a
    # code from the currently shown link is never pasted into a newer process.
    loop = asyncio.get_running_loop()
    overall_deadline = loop.time() + _AUTH_TOTAL_WAIT_SECONDS
    last_uri = ""
    while loop.time() < overall_deadline:
        remaining = overall_deadline - loop.time()
        if remaining < 5:
            break
        if invocation_id:
            clear_auth_input_queue(invocation_id)
        async for event in _oauth_session_attempt(
            cli_path,
            invocation_id=invocation_id,
            session_budget=remaining,
        ):
            if event.type is ProviderEventType.AUTH_REQUIRED:
                uri = str(event.payload.get("verification_uri") or "")
                if uri and uri != last_uri:
                    last_uri = uri
                    yield event
                continue
            yield event
            return

    yield error_event(
        "provider_auth_timeout",
        "Google Antigravity sign-in timed out waiting for authorization code",
        retryable=True,
    )


async def _oauth_session_attempt(
    cli_path: str,
    *,
    invocation_id: str,
    session_budget: float,
) -> AsyncGenerator[ProviderEventV1, None]:
    master_fd, slave_fd = pty.openpty()
    process: asyncio.subprocess.Process | None = None
    try:
        process = await asyncio.create_subprocess_exec(
            cli_path,
            "-p",
            "ping",
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=_cli_env(),
            start_new_session=True,
        )
    except OSError:
        _close_fd(master_fd)
        _close_fd(slave_fd)
        yield error_event("provider_auth_failed", "Failed to start Antigravity CLI for OAuth")
        return
    finally:
        _close_fd(slave_fd)

    verification_uri = ""
    scan_buffer = ""
    loop = asyncio.get_running_loop()
    # Do not self-timeout before the CLI does — killing early orphans the PKCE verifier.
    session_deadline = loop.time() + max(5.0, session_budget)
    url_deadline = loop.time() + min(_AUTH_URL_WAIT_SECONDS, session_budget)
    code_written = False
    try:
        while not verification_uri and loop.time() < url_deadline:
            if process.returncode is not None:
                break
            try:
                chunk = await asyncio.wait_for(
                    asyncio.to_thread(os.read, master_fd, _PTY_READ_CHUNK),
                    timeout=max(0.1, min(1.0, url_deadline - loop.time())),
                )
            except TimeoutError:
                continue
            except OSError:
                break
            if not chunk:
                break
            scan_buffer = (scan_buffer + chunk.decode("utf-8", errors="replace"))[-16384:]
            verification_uri = parse_antigravity_oauth_url(scan_buffer)

        if not verification_uri:
            await _stop_process(process)
            return

        oauth_state = parse_antigravity_oauth_state(verification_uri)
        yield ProviderEventV1(
            ProviderEventType.AUTH_REQUIRED,
            {
                "verification_uri": verification_uri,
                "user_code": oauth_state,
                "oauth_state": oauth_state,
                "expires_in": _AUTH_LINK_TTL_SECONDS,
                "accepts_authorization_code": True,
            },
        )

        code_task: asyncio.Task[AuthInputMessage | None] | None = None
        if invocation_id:
            code_task = asyncio.create_task(
                wait_auth_input(invocation_id, timeout=max(1.0, session_deadline - loop.time()))
            )

        while process.returncode is None and loop.time() < session_deadline:
            if code_task is not None and code_task.done() and not code_written:
                message = code_task.result()
                code_task = None
                if message is None:
                    break
                if oauth_state and message.oauth_state and message.oauth_state != oauth_state:
                    yield error_event(
                        "provider_auth_session_mismatch",
                        "Authorization code belongs to a previous sign-in link; open the latest link and paste a fresh code",
                    )
                    return
                await _write_auth_code_to_pty(master_fd, message.authorization_code)
                code_written = True
                drain_deadline = loop.time() + _AUTH_CODE_DRAIN_SECONDS
                while process.returncode is None and loop.time() < drain_deadline:
                    try:
                        chunk = await asyncio.wait_for(
                            asyncio.to_thread(os.read, master_fd, _PTY_READ_CHUNK),
                            timeout=0.5,
                        )
                    except TimeoutError:
                        continue
                    except OSError:
                        break
                    if chunk:
                        scan_buffer = (scan_buffer + chunk.decode("utf-8", errors="replace"))[-16384:]
                if process.returncode is None:
                    try:
                        await asyncio.wait_for(process.wait(), timeout=30)
                    except TimeoutError:
                        await _stop_process(process)
                scan_buffer = await _drain_pty_tail(master_fd, scan_buffer)
                if process.returncode == 0:
                    yield ProviderEventV1(ProviderEventType.COMPLETED, {"authenticated": True})
                else:
                    code, message_text, detail = _auth_failure_from_output(scan_buffer)
                    event = error_event(code, message_text)
                    if detail:
                        event = ProviderEventV1(event.type, {**event.payload, **detail})
                    yield event
                return

            try:
                chunk = await asyncio.wait_for(
                    asyncio.to_thread(os.read, master_fd, _PTY_READ_CHUNK),
                    timeout=0.5,
                )
            except TimeoutError:
                continue
            except OSError:
                break
            if chunk:
                scan_buffer = (scan_buffer + chunk.decode("utf-8", errors="replace"))[-16384:]

        if code_task is not None and not code_task.done():
            code_task.cancel()
            await asyncio.gather(code_task, return_exceptions=True)
        # CLI exited or envelope ended without a code — rotate to a fresh PKCE URL.
        if not code_written:
            await _stop_process(process)
            return
        if process.returncode == 0:
            yield ProviderEventV1(ProviderEventType.COMPLETED, {"authenticated": True})
        else:
            scan_buffer = await _drain_pty_tail(master_fd, scan_buffer)
            code, message_text, detail = _auth_failure_from_output(scan_buffer)
            event = error_event(code, message_text)
            if detail:
                event = ProviderEventV1(event.type, {**event.payload, **detail})
            yield event
    except Exception:  # noqa: BLE001 - never crash the runner process for auth failures
        await _stop_process(process)
        yield error_event("provider_auth_failed", "Google Antigravity authentication failed")
    finally:
        await _stop_process(process)
        _close_fd(master_fd)


async def _write_auth_code_to_pty(master_fd: int, authorization_code: str) -> None:
    # CLI prompt uses CRLF; send LF (accepted) without bracketed-paste wrappers.
    payload = (authorization_code.strip() + "\n").encode("utf-8")
    try:
        await asyncio.to_thread(os.write, master_fd, payload)
    except OSError:
        return


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


async def _drain_pty_tail(master_fd: int, scan_buffer: str) -> str:
    """Read any final CLI bytes after process exit (error lines often arrive here)."""
    buffer = scan_buffer
    for _ in range(32):
        try:
            chunk = await asyncio.wait_for(
                asyncio.to_thread(os.read, master_fd, _PTY_READ_CHUNK),
                timeout=0.05,
            )
        except (TimeoutError, OSError):
            break
        if not chunk:
            break
        buffer = (buffer + chunk.decode("utf-8", errors="replace"))[-16384:]
    return buffer


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
    if "invalid_grant" in lowered:
        return (
            "provider_auth_failed",
            "Google rejected the authorization code (invalid_grant). Open the current link and paste a fresh code once within ~55s",
            detail,
        )
    if "invalid_request" in lowered or "redirect_uri" in lowered:
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


async def _stop_process(process: asyncio.subprocess.Process | None) -> None:
    if process is None:
        return
    if process.returncode is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
        return
    except (TimeoutError, ProcessLookupError):
        pass
    try:
        process.kill()
    except ProcessLookupError:
        return
    try:
        await process.wait()
    except ProcessLookupError:
        return


def _close_fd(fd: int) -> None:
    if fd < 0:
        return
    try:
        os.close(fd)
    except OSError:
        pass
