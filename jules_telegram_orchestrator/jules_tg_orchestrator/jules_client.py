from __future__ import annotations

from typing import Any

import httpx


class JulesApiError(RuntimeError):
    pass


class JulesClient:
    def __init__(self, *, api_key: str, base_url: str = "https://jules.googleapis.com/v1alpha") -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            timeout=httpx.Timeout(40.0, connect=15.0),
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = await self.client.request(method, path, **kwargs)
        if response.status_code >= 400:
            body = response.text[:1200]
            raise JulesApiError(f"Jules API {response.status_code}: {body}")
        if not response.content:
            return {}
        return response.json()

    async def list_sources(self, *, page_size: int = 100) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        page_token = ""
        while True:
            params: dict[str, Any] = {"pageSize": page_size}
            if page_token:
                params["pageToken"] = page_token
            payload = await self._request("GET", "/sources", params=params)
            sources.extend(payload.get("sources") or [])
            page_token = payload.get("nextPageToken") or ""
            if not page_token:
                return sources

    async def resolve_source(self, source_hint: str) -> str:
        source_hint = source_hint.strip()
        if source_hint.startswith("sources/"):
            return source_hint

        normalized = source_hint.removeprefix("github/")
        sources = await self.list_sources()
        for source in sources:
            name = source.get("name", "")
            source_id = source.get("id", "")
            repo = source.get("githubRepo") or {}
            full_repo = f"{repo.get('owner', '')}/{repo.get('repo', '')}".strip("/")
            if source_hint in {name, source_id} or normalized == full_repo:
                return name

        raise JulesApiError(f"Could not resolve Jules source: {source_hint}")

    async def create_session(
        self,
        *,
        prompt: str,
        title: str,
        source: str,
        branch: str,
        require_plan_approval: bool,
        auto_create_pr: bool,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "prompt": prompt,
            "title": title,
            "sourceContext": {
                "source": source,
                "githubRepoContext": {"startingBranch": branch},
            },
            "requirePlanApproval": require_plan_approval,
        }
        if auto_create_pr:
            body["automationMode"] = "AUTO_CREATE_PR"
        return await self._request("POST", "/sessions", json=body)

    async def list_sessions(self, *, page_size: int = 30) -> list[dict[str, Any]]:
        payload = await self._request("GET", "/sessions", params={"pageSize": page_size})
        return payload.get("sessions") or []

    async def get_session(self, session_id: str) -> dict[str, Any]:
        session_id = session_id.removeprefix("sessions/")
        return await self._request("GET", f"/sessions/{session_id}")

    async def list_activities(self, session_id: str, *, page_size: int = 50) -> list[dict[str, Any]]:
        session_id = session_id.removeprefix("sessions/")
        payload = await self._request("GET", f"/sessions/{session_id}/activities", params={"pageSize": page_size})
        return payload.get("activities") or []

    async def send_message(self, session_id: str, prompt: str) -> None:
        session_id = session_id.removeprefix("sessions/")
        await self._request("POST", f"/sessions/{session_id}:sendMessage", json={"prompt": prompt})

    async def approve_plan(self, session_id: str) -> None:
        session_id = session_id.removeprefix("sessions/")
        await self._request("POST", f"/sessions/{session_id}:approvePlan", json={})
