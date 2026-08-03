"""Process-local, event-loop-owned SSH connection pool for short HTTP operations."""

from __future__ import annotations

import asyncio
import atexit
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

import asyncssh
from asgiref.sync import sync_to_async
from django.conf import settings

from servers.ssh_host_keys import build_server_connect_kwargs, ensure_server_known_hosts
from servers.ssh_private_keys import get_server_private_key_text


class SSHConnectionPoolExhausted(RuntimeError):
    pass


@dataclass
class _ConnectionEntry:
    connection: Any
    server_id: int
    user_id: int
    last_used: float
    in_use: int = 0


@dataclass
class _SFTPSession:
    entry: _ConnectionEntry
    context: Any
    client: Any


class _RemoteFile:
    def __init__(self, pool: SSHConnectionPool, session_id: str, file_id: str):
        self._pool = pool
        self._session_id = session_id
        self._file_id = file_id

    async def read(self, *args, **kwargs):
        return await self._pool._submit(self._pool._call_file(self._session_id, self._file_id, "read", args, kwargs))

    async def write(self, *args, **kwargs):
        return await self._pool._submit(self._pool._call_file(self._session_id, self._file_id, "write", args, kwargs))

    async def close(self) -> None:
        await self._pool._submit(self._pool._close_file(self._session_id, self._file_id))


class _RemoteFileContext:
    def __init__(self, proxy: PooledSFTPClient, args: tuple, kwargs: dict):
        self._proxy = proxy
        self._args = args
        self._kwargs = kwargs
        self._file: _RemoteFile | None = None

    async def __aenter__(self) -> _RemoteFile:
        file_id = await self._proxy._pool._submit(
            self._proxy._pool._open_file(self._proxy._session_id, self._args, self._kwargs)
        )
        self._file = _RemoteFile(self._proxy._pool, self._proxy._session_id, file_id)
        return self._file

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._file is not None:
            await self._file.close()


class PooledSFTPClient:
    """Small cross-loop proxy covering the SFTP surface used by ``servers.sftp``."""

    def __init__(self, pool: SSHConnectionPool, session_id: str):
        self._pool = pool
        self._session_id = session_id

    def __getattr__(self, name: str):
        async def method(*args, **kwargs):
            return await self._pool._submit(self._pool._call_sftp(self._session_id, name, args, kwargs))

        return method

    def scandir(self, *args, **kwargs):
        async def iterator():
            items = await self._pool._submit(self._pool._scan_sftp(self._session_id, args, kwargs))
            for item in items:
                yield item

        return iterator()

    def open(self, *args, **kwargs) -> _RemoteFileContext:
        return _RemoteFileContext(self, args, kwargs)

    async def close(self) -> None:
        await self._pool._submit(self._pool._close_sftp(self._session_id))


class SSHConnectionPool:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready = threading.Event()
        self._connections: OrderedDict[tuple[int, int], _ConnectionEntry] = OrderedDict()
        self._sftp_sessions: dict[str, _SFTPSession] = {}
        self._files: dict[tuple[str, str], Any] = {}

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is not None and self._thread is not None and self._thread.is_alive():
            return self._loop
        self._ready.clear()

        def runner() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            self._ready.set()
            loop.run_forever()
            loop.run_until_complete(self._close_all())
            loop.close()

        self._thread = threading.Thread(target=runner, name="ssh-connection-pool", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)
        if self._loop is None:
            raise RuntimeError("SSH connection pool event loop did not start")
        return self._loop

    async def _submit(self, coroutine):
        loop = self._ensure_loop()
        if asyncio.get_running_loop() is loop:
            return await coroutine
        future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        return await asyncio.wrap_future(future)

    @staticmethod
    def _limits() -> tuple[float, int, int]:
        return (
            max(1.0, float(getattr(settings, "SSH_POOL_IDLE_TTL_SECONDS", 60))),
            max(1, int(getattr(settings, "SSH_POOL_MAX_PER_SERVER", 4))),
            max(1, int(getattr(settings, "SSH_POOL_MAX_CONNECTIONS", 50))),
        )

    @staticmethod
    def _closed(connection: Any) -> bool:
        checker = getattr(connection, "is_closed", None)
        return bool(checker()) if callable(checker) else False

    async def _close_entry(self, key: tuple[int, int], entry: _ConnectionEntry) -> None:
        self._connections.pop(key, None)
        entry.connection.close()
        waiter = getattr(entry.connection, "wait_closed", None)
        if callable(waiter):
            await waiter()

    async def _evict_expired(self) -> None:
        ttl, _per_server, _global = self._limits()
        cutoff = time.monotonic() - ttl
        for key, entry in list(self._connections.items()):
            if entry.in_use == 0 and (entry.last_used <= cutoff or self._closed(entry.connection)):
                await self._close_entry(key, entry)

    async def _make_room(self, server_id: int) -> None:
        await self._evict_expired()
        _ttl, per_server, global_limit = self._limits()

        async def evict_one(candidates: list[tuple[tuple[int, int], _ConnectionEntry]]) -> bool:
            for key, entry in candidates:
                if entry.in_use == 0:
                    await self._close_entry(key, entry)
                    return True
            return False

        while sum(1 for entry in self._connections.values() if entry.server_id == server_id) >= per_server:
            candidates = [(key, entry) for key, entry in self._connections.items() if entry.server_id == server_id]
            if not await evict_one(candidates):
                raise SSHConnectionPoolExhausted("SSH per-server connection limit reached")
        while len(self._connections) >= global_limit:
            if not await evict_one(list(self._connections.items())):
                raise SSHConnectionPoolExhausted("SSH global connection limit reached")

    async def _acquire(self, key: tuple[int, int], connect_kwargs: dict[str, Any]) -> _ConnectionEntry:
        await self._evict_expired()
        entry = self._connections.get(key)
        if entry is not None and not self._closed(entry.connection):
            entry.in_use += 1
            entry.last_used = time.monotonic()
            self._connections.move_to_end(key)
            return entry
        if entry is not None:
            await self._close_entry(key, entry)
        await self._make_room(key[0])
        connection = await asyncssh.connect(**connect_kwargs)
        entry = _ConnectionEntry(
            connection=connection,
            server_id=key[0],
            user_id=key[1],
            last_used=time.monotonic(),
            in_use=1,
        )
        self._connections[key] = entry
        return entry

    def _release(self, key: tuple[int, int], entry: _ConnectionEntry) -> None:
        entry.in_use = max(0, entry.in_use - 1)
        entry.last_used = time.monotonic()
        if key in self._connections:
            self._connections.move_to_end(key)

    async def _connect_kwargs(self, server, secret: str) -> dict[str, Any]:
        known_hosts = await ensure_server_known_hosts(server)
        private_key_text = ""
        if str(getattr(server, "auth_method", "") or "") in {"key", "key_password"}:
            private_key_text = await sync_to_async(get_server_private_key_text, thread_sensitive=True)(server)
        return build_server_connect_kwargs(
            server,
            secret=secret,
            private_key_text=private_key_text,
            known_hosts=known_hosts,
        )

    async def open_sftp(self, server, *, user_id: int | None = None, secret: str = "") -> PooledSFTPClient:
        key = (int(server.pk), int(user_id or server.user_id))
        connect_kwargs = await self._connect_kwargs(server, secret)
        session_id = await self._submit(self._open_sftp(key, connect_kwargs))
        return PooledSFTPClient(self, session_id)

    async def _open_sftp(self, key: tuple[int, int], connect_kwargs: dict[str, Any]) -> str:
        entry = await self._acquire(key, connect_kwargs)
        try:
            context = entry.connection.start_sftp_client()
            client = await context.__aenter__()
        except Exception:
            self._release(key, entry)
            raise
        session_id = uuid.uuid4().hex
        self._sftp_sessions[session_id] = _SFTPSession(entry=entry, context=context, client=client)
        return session_id

    async def _call_sftp(self, session_id: str, name: str, args: tuple, kwargs: dict):
        session = self._sftp_sessions[session_id]
        result = getattr(session.client, name)(*args, **kwargs)
        return await result if hasattr(result, "__await__") else result

    async def _scan_sftp(self, session_id: str, args: tuple, kwargs: dict) -> list[Any]:
        session = self._sftp_sessions[session_id]
        return [item async for item in session.client.scandir(*args, **kwargs)]

    async def _open_file(self, session_id: str, args: tuple, kwargs: dict) -> str:
        session = self._sftp_sessions[session_id]
        file_obj = await session.client.open(*args, **kwargs)
        file_id = uuid.uuid4().hex
        self._files[(session_id, file_id)] = file_obj
        return file_id

    async def _call_file(self, session_id: str, file_id: str, name: str, args: tuple, kwargs: dict):
        file_obj = self._files[(session_id, file_id)]
        result = getattr(file_obj, name)(*args, **kwargs)
        return await result if hasattr(result, "__await__") else result

    async def _close_file(self, session_id: str, file_id: str) -> None:
        file_obj = self._files.pop((session_id, file_id), None)
        if file_obj is None:
            return
        result = file_obj.close()
        if hasattr(result, "__await__"):
            await result
        waiter = getattr(file_obj, "wait_closed", None)
        if callable(waiter):
            await waiter()

    async def _close_sftp(self, session_id: str) -> None:
        session = self._sftp_sessions.pop(session_id, None)
        if session is None:
            return
        for current_session, file_id in list(self._files):
            if current_session == session_id:
                await self._close_file(current_session, file_id)
        try:
            await session.context.__aexit__(None, None, None)
        finally:
            key = (session.entry.server_id, session.entry.user_id)
            self._release(key, session.entry)

    async def run_command(
        self,
        server,
        command: str,
        *,
        user_id: int | None = None,
        secret: str = "",
        **run_kwargs,
    ):
        key = (int(server.pk), int(user_id or server.user_id))
        connect_kwargs = await self._connect_kwargs(server, secret)
        return await self._submit(self._run_command(key, connect_kwargs, command, run_kwargs))

    async def _run_command(self, key, connect_kwargs, command, run_kwargs):
        entry = await self._acquire(key, connect_kwargs)
        try:
            return await entry.connection.run(command, **run_kwargs)
        finally:
            self._release(key, entry)

    async def _invalidate(self, server_id: int, user_id: int | None = None) -> int:
        closed = 0
        for key, entry in list(self._connections.items()):
            if key[0] != int(server_id) or (user_id is not None and key[1] != int(user_id)):
                continue
            if entry.in_use:
                entry.connection.close()
            await self._close_entry(key, entry)
            closed += 1
        return closed

    def invalidate(self, server_id: int, user_id: int | None = None) -> None:
        if self._loop is None or not self._loop.is_running():
            return
        asyncio.run_coroutine_threadsafe(self._invalidate(server_id, user_id), self._loop)

    async def stats(self) -> dict[str, Any]:
        return await self._submit(self._stats())

    async def _stats(self) -> dict[str, Any]:
        await self._evict_expired()
        now = time.monotonic()
        ages = [max(0.0, now - entry.last_used) for entry in self._connections.values()]
        return {
            "active_connections": len(self._connections),
            "in_use_connections": sum(1 for entry in self._connections.values() if entry.in_use),
            "oldest_idle_seconds": max(ages, default=0.0),
        }

    async def _close_all(self) -> None:
        for session_id in list(self._sftp_sessions):
            await self._close_sftp(session_id)
        for key, entry in list(self._connections.items()):
            await self._close_entry(key, entry)

    def shutdown(self) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        future = asyncio.run_coroutine_threadsafe(self._close_all(), loop)
        try:
            future.result(timeout=5)
        finally:
            loop.call_soon_threadsafe(loop.stop)


ssh_connection_pool = SSHConnectionPool()


def invalidate_ssh_connections(server_id: int, user_id: int | None = None) -> None:
    ssh_connection_pool.invalidate(server_id, user_id)


atexit.register(ssh_connection_pool.shutdown)
