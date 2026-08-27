from __future__ import annotations

import urllib.parse

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

from kubernetes_ops.permissions import kubernetes_permission_policy
from kubernetes_ops.services.admin_resources import AdminResourceError
from kubernetes_ops.services.admin_streams import (
    active_admin_stream_session_status,
    close_admin_stream,
)


class KubernetesAdminConsumerAuthMixin:
    async def _authenticated(self) -> bool:
        user = self.scope.get("user")
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            return False
        policy = await database_sync_to_async(kubernetes_permission_policy)(user)
        return bool(policy["can_read"])

    def _query_params(self) -> dict[str, str]:
        raw = self.scope.get("query_string", b"").decode("utf-8", errors="ignore")
        parsed = urllib.parse.parse_qs(raw, keep_blank_values=True)
        return {key: values[-1] if values else "" for key, values in parsed.items()}


class KubernetesAdminFollowLifecycleMixin(KubernetesAdminConsumerAuthMixin):
    _active_stream: dict | None = None
    _last_payload: dict | None = None
    _batch_count: int = 0
    _stream_finalized: bool = False

    def _track_follow_stream(self, stream: dict, initial_payload: dict) -> None:
        self._active_stream = stream
        self._last_payload = initial_payload
        self._batch_count = 0
        self._stream_finalized = False

    def _track_follow_batch(self, payload: dict, batch_count: int) -> None:
        self._last_payload = payload
        self._batch_count = batch_count

    async def _close_active_stream(self, close_reason: str) -> dict | None:
        stream = self._active_stream
        if not stream or self._stream_finalized:
            return None
        self._stream_finalized = True
        return await database_sync_to_async(close_admin_stream)(
            user=self.scope["user"],
            stream=stream,
            last_payload=self._last_payload
            or {"target": stream.get("target", {}), "source": "not_started", "available": False},
            batch_count=self._batch_count,
            close_reason=close_reason,
        )

    async def _active_stream_session_close_reason(self, stream: dict) -> str:
        state = await database_sync_to_async(active_admin_stream_session_status)(session_pk=stream["session_pk"])
        if state.get("active"):
            return ""
        last_payload = dict(
            self._last_payload or {"target": stream.get("target", {}), "source": "not_started", "available": False}
        )
        last_payload["session_status"] = str(state.get("status") or "")
        self._last_payload = last_payload
        return str(state.get("code") or "admin_session_not_active")

    async def _fail_active_stream(self, stream: dict, exc: AdminResourceError) -> None:
        self._stream_finalized = True
        await self._fail_stream(stream, exc)

    async def disconnect(self, code):
        await self._close_active_stream("client_disconnect")
