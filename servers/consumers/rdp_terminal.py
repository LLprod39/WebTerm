"""
WebSocket consumer for RDP (Guacamole) in-browser sessions.
Proxies Guacamole protocol between browser and guacd.
"""

from __future__ import annotations

import asyncio
import contextlib
import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.db.models import Q
from django.utils import timezone
from loguru import logger

from core_ui.activity import log_user_activity_async
from servers.guacd_tunnel import _parse_guac_instruction, connect_guacd_rdp
from servers.models import Server
from servers.secret_utils import get_server_auth_secret


class RDPTerminalConsumer(AsyncWebsocketConsumer):
    """
    Accepts WebSocket at /ws/servers/<server_id>/rdp/.
    Expects first message: JSON { "master_password": "...", "password": "...", "domain": "..." } (all optional).
    If master_password is omitted, uses MASTER_PASSWORD from environment.
    Then switches to binary Guacamole protocol: we send args, then proxy guacd <-> client.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.server_id = None
        self.user = None
        self.server = None
        self.guacd_reader: asyncio.StreamReader | None = None
        self.guacd_writer: asyncio.StreamWriter | None = None
        self._pipe_task: asyncio.Task | None = None
        self._starting_guacd = False
        self._client_disconnected = False
        self._rdp_domain = ""
        self._guac_text_tail = ""

    async def connect(self):
        self.server_id = self.scope["url_route"]["kwargs"].get("server_id")
        if not self.server_id:
            await self.close(code=4400)
            return
        self.user = self.scope.get("user")
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4403)
            return
        server = await self._get_server(int(self.server_id))
        if not server or not server.is_rdp():
            await self.close(code=4404)
            return
        self.server = server
        self.guacd_reader = None
        self.guacd_writer = None
        self._pipe_task = None
        self._starting_guacd = False
        self._client_disconnected = False
        self._rdp_domain = ""
        self._guac_text_tail = ""
        logger.info("RDP WS connected: server_id={} user_id={}", self.server_id, getattr(self.user, "id", None))
        await self.accept()

    @database_sync_to_async
    def _get_server(self, server_id: int) -> Server | None:
        now = timezone.now()
        return (
            Server.objects.filter(id=server_id, is_active=True)
            .filter(
                Q(user_id=self.user.id)
                | (
                    Q(shares__user_id=self.user.id, shares__is_revoked=False)
                    & (Q(shares__expires_at__isnull=True) | Q(shares__expires_at__gt=now))
                )
            )
            .distinct()
            .first()
        )

    async def receive(self, text_data=None, bytes_data=None):
        # First message is expected to be auth payload for resolving stored secrets.
        # After guacd is started, all Guacamole instructions must pass through as-is
        # (including sync/input). Waiting for client-side "connect" causes deadlock.
        if not self.guacd_writer and (text_data or bytes_data):
            if self._starting_guacd:
                return
            raw = text_data if text_data is not None else (bytes_data.decode("utf-8", errors="replace") if bytes_data else None)
            if raw and raw.strip().startswith("{"):
                try:
                    data = json.loads(raw)
                    master_password = (data.get("master_password") or "").strip()
                    plain_password = (data.get("password") or "").strip()
                    domain = (data.get("domain") or "").strip()
                except Exception:
                    master_password = ""
                    plain_password = ""
                    domain = ""
                self._rdp_domain = domain
                password_source = "direct" if plain_password else "stored"
                logger.info(
                    "RDP auth input: server_id={} source={} master_provided={} plain_len={} domain={}",
                    self.server_id,
                    password_source,
                    bool(master_password),
                    len(plain_password),
                    domain,
                )
                try:
                    password = await self._resolve_password(master_password, plain_password)
                except ValueError as e:
                    logger.warning("RDP invalid master password: server_id={}", self.server_id)
                    await self._send_ws_error(str(e), "invalid_master_password")
                    return
                self._starting_guacd = True
                try:
                    await self._start_guacd(password, self._rdp_domain)
                finally:
                    self._starting_guacd = False
                return
            if raw and (raw[0].isdigit() or "select" in raw[:20]):
                password = await self._resolve_password("", "")
                self._starting_guacd = True
                try:
                    await self._start_guacd(password, self._rdp_domain)
                finally:
                    self._starting_guacd = False
                return

        data = bytes_data if bytes_data is not None else (text_data.encode("utf-8") if text_data else None)
        if data is None or not self.guacd_writer:
            return
        try:
            self.guacd_writer.write(data)
            await self.guacd_writer.drain()
        except Exception as e:
            logger.warning("RDP write to guacd failed (server_id={}): {}", self.server_id, e)
            await self._send_ws_error("RDP session write failed", "guacd_write_failed")
            await self.close(code=4500)

    @database_sync_to_async
    def _resolve_password(self, master_password: str, plain: str) -> str:
        if plain:
            return plain
        if self.server.auth_method not in ("password", "key_password"):
            return ""
        try:
            return get_server_auth_secret(
                self.server,
                master_password=(master_password or "").strip(),
                fallback_plain=plain,
            )
        except ValueError as exc:
            raise ValueError("Invalid master password") from exc

    async def _start_guacd(self, password: str, domain: str = ""):
        try:
            port = self.server.get_rdp_port()
            self.guacd_reader, self.guacd_writer, args_line = await connect_guacd_rdp(
                host=self.server.host,
                port=port,
                username=self.server.username,
                password=password,
                domain=domain or "",
            )
            logger.info(
                "RDP guacd handshake success: server_id={} host={} port={} user={} domain={}",
                self.server_id, self.server.host, port, self.server.username, domain or "",
            )
            await self._ingest_memory_event(
                event_type="rdp_session_opened",
                raw_text="RDP session opened",
                payload={
                    "host": self.server.host,
                    "port": port,
                    "username": self.server.username,
                    "domain": domain or "",
                },
                importance_hint=0.52,
                force_compact=True,
            )
            await log_user_activity_async(
                user_id=getattr(self.user, "id", None),
                category='servers',
                action='rdp_connect',
                status='success',
                description=f'Connected to RDP server "{self.server.name}"',
                entity_type='server',
                entity_id=self.server.id if self.server else '',
                entity_name=self.server.name if self.server else '',
                metadata={
                    'host': self.server.host if self.server else '',
                    'port': port,
                },
            )
        except Exception as e:
            err_msg = str(e) or "Unknown error"
            logger.exception("RDP guacd handshake failed (server_id={}): {}", self.server_id, err_msg)
            await log_user_activity_async(
                user_id=getattr(self.user, "id", None),
                category='servers',
                action='rdp_connect',
                status='error',
                description=f'RDP connect failed: {err_msg}',
                entity_type='server',
                entity_id=self.server.id if self.server else '',
                entity_name=self.server.name if self.server else '',
            )
            await self._send_ws_error(err_msg, "guacd_failed")
            await self.close(code=4500)
            return

        await self.send(text_data=args_line)
        self._pipe_task = asyncio.create_task(self._pipe_guacd_to_ws())

    async def _pipe_guacd_to_ws(self):
        eof = False
        remote_error = False
        try:
            while self.guacd_reader:
                data = await self.guacd_reader.read(65536)
                if not data:
                    eof = True
                    break

                error_message, error_code = self._extract_guacd_error(data)
                if error_message:
                    normalized = "rdp_remote_error"
                    if "authentication failure" in error_message.lower():
                        normalized = "rdp_auth_failed"
                    code_suffix = f" ({error_code})" if error_code else ""
                    logger.warning(
                        "RDP remote error: server_id={} message={} code={}",
                        self.server_id, error_message, error_code or "",
                    )
                    await self._send_ws_error(f"{error_message}{code_suffix}", normalized)
                    remote_error = True
                    break

                await self.send(bytes_data=data)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("RDP guacd pipe error (server_id={}): {}", self.server_id, e)
            await self._send_ws_error("RDP session stream failed", "guacd_pipe_failed")
        finally:
            await self._close_guacd()
            if not self._client_disconnected:
                if eof and not remote_error:
                    await self._send_ws_error("RDP session closed by remote host", "rdp_closed")
                with contextlib.suppress(Exception):
                    await self.close(code=4501 if eof else 4500)

    def _extract_guacd_error(self, chunk: bytes) -> tuple[str, str] | tuple[None, None]:
        text = chunk.decode("utf-8", errors="ignore")
        if not text:
            return None, None

        data = self._guac_text_tail + text
        marker = ".error,"
        idx = data.find(marker)
        if idx == -1:
            self._guac_text_tail = data[-8192:]
            return None, None

        start = data.rfind(";", 0, idx)
        start = 0 if start == -1 else start + 1
        end = data.find(";", idx)
        if end == -1:
            self._guac_text_tail = data[-8192:]
            return None, None

        instruction = data[start:end + 1]
        self._guac_text_tail = data[end + 1:][-8192:]

        parts = _parse_guac_instruction(instruction)
        if not parts or parts[0] != "error":
            return None, None
        message = parts[1] if len(parts) > 1 else "RDP remote error"
        code = parts[2] if len(parts) > 2 else ""
        return message, code

    async def _close_guacd(self):
        if self.guacd_writer:
            try:
                self.guacd_writer.close()
                await self.guacd_writer.wait_closed()
            except Exception:
                pass
            self.guacd_writer = None
        self.guacd_reader = None

    async def _send_ws_error(self, message: str, code: str):
        logger.warning("RDP WS error: server_id={} code={} message={}", self.server_id, code, message)
        with contextlib.suppress(Exception):
            await self.send(text_data=json.dumps({"error": message, "code": code}))

    async def disconnect(self, close_code):
        logger.info("RDP WS disconnected: server_id={} close_code={}", self.server_id, close_code)
        was_connected = bool(self.guacd_writer or self.guacd_reader)
        self._client_disconnected = True
        if self._pipe_task and not self._pipe_task.done():
            self._pipe_task.cancel()
            with contextlib.suppress(Exception):
                await self._pipe_task
        self._pipe_task = None
        await self._close_guacd()
        if was_connected and self.server:
            await self._ingest_memory_event(
                event_type="rdp_session_closed",
                raw_text=self._guac_text_tail[-1200:] if self._guac_text_tail else "RDP session closed",
                payload={"close_code": close_code},
                importance_hint=0.48,
                force_compact=True,
            )
            await log_user_activity_async(
                user_id=getattr(self.user, "id", None),
                category='servers',
                action='rdp_disconnect',
                status='info',
                description=f'Disconnected from RDP server "{self.server.name}"',
                entity_type='server',
                entity_id=self.server.id,
                entity_name=self.server.name,
            )

    @database_sync_to_async
    def _ingest_memory_event(
        self,
        *,
        event_type: str,
        raw_text: str,
        payload: dict,
        importance_hint: float,
        force_compact: bool = False,
    ) -> None:
        from app.agent_kernel.memory.store import DjangoServerMemoryStore

        if not self.server:
            return
        session_key = f"rdp:{self.server.id}:{getattr(self.user, 'id', 'anon')}"
        DjangoServerMemoryStore()._ingest_event_sync(
            self.server.id,
            source_kind="rdp",
            actor_kind="human",
            source_ref=session_key,
            session_id=session_key,
            event_type=event_type,
            raw_text=raw_text,
            structured_payload=payload,
            importance_hint=importance_hint,
            actor_user_id=getattr(self.user, "id", None),
            force_compact=force_compact,
        )
