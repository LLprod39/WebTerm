from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import aiohttp


def _base_http(url: str) -> str:
    return url.rstrip("/") + "/"


def _base_ws(url: str) -> str:
    base = url.rstrip("/")
    if base.startswith("https://"):
        return "wss://" + base[len("https://"):]
    if base.startswith("http://"):
        return "ws://" + base[len("http://"):]
    raise ValueError(f"Unsupported base URL: {url}")


class SmokeFailure(RuntimeError):
    pass


async def _expect_json(
    ws: aiohttp.ClientWebSocketResponse,
    *,
    timeout: float = 20.0,
    predicate=None,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error: str | None = None
    while time.monotonic() < deadline:
        msg = await ws.receive(timeout=timeout)
        if msg.type == aiohttp.WSMsgType.TEXT:
            payload = json.loads(msg.data)
            if payload.get("type") == "error" and payload.get("fatal"):
                raise SmokeFailure(str(payload.get("message") or "fatal websocket error"))
            if predicate is None or predicate(payload):
                return payload
            continue
        if msg.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED}:
            raise SmokeFailure(f"websocket closed before expected payload: {last_error or 'closed'}")
        if msg.type == aiohttp.WSMsgType.ERROR:
            raise SmokeFailure(f"websocket receive error: {ws.exception()}")
    raise SmokeFailure(f"timed out waiting for websocket payload: {last_error or 'no match'}")


async def _poll_run(
    session: aiohttp.ClientSession,
    *,
    base_url: str,
    run_id: int,
    headers: dict[str, str] | None = None,
    timeout: float = 90.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        async with session.get(urljoin(base_url, f"api/studio/runs/{run_id}/"), headers=headers) as response:
            try:
                payload = await response.json()
            except aiohttp.ContentTypeError:
                payload = {"raw_text": await response.text()}
            if response.status != 200:
                raise SmokeFailure(f"run detail failed: HTTP {response.status} {payload}")
            status = str(payload.get("status") or "")
            if status in {"completed", "failed", "stopped"}:
                return payload
        await asyncio.sleep(1)
    raise SmokeFailure(f"timed out waiting for pipeline run {run_id}")


async def _get_agent_run_detail(
    session: aiohttp.ClientSession,
    *,
    base_url: str,
    run_id: int,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    async with session.get(
        urljoin(base_url, f"servers/api/agents/runs/{run_id}/"),
        headers=headers,
    ) as response:
        try:
            payload = await response.json()
        except aiohttp.ContentTypeError:
            payload = {"raw_text": await response.text()}
        if response.status != 200:
            raise SmokeFailure(f"agent run detail failed: HTTP {response.status} {payload}")
        return payload


class SmokeUserSession:
    def __init__(self, *, base_url: str, seed: dict[str, Any], shared_password: str):
        self.base_url = _base_http(base_url)
        self.ws_base = _base_ws(base_url)
        self.seed = seed
        self.password = shared_password
        self.session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
        self.ws_token = ""
        self.csrf_token = ""
        self.csrf_cookie = ""
        self.session_cookie = ""

    def _cookie_header(self) -> str:
        parts: list[str] = []
        if self.csrf_cookie or self.csrf_token:
            parts.append(f"csrftoken={self.csrf_cookie or self.csrf_token}")
        if self.session_cookie:
            parts.append(f"sessionid={self.session_cookie}")
        return "; ".join(parts)

    async def close(self) -> None:
        await self.session.close()

    async def login(self) -> None:
        async with self.session.get(urljoin(self.base_url, "api/auth/csrf/")) as response:
            if response.status != 200:
                raise SmokeFailure(f"csrf failed for {self.seed['username']}: HTTP {response.status}")
            payload = await response.json()
            self.csrf_token = str(payload.get("csrfToken") or "")
            self.csrf_cookie = str(response.cookies.get("csrftoken").value if response.cookies.get("csrftoken") else "")

        headers = {
            "Content-Type": "application/json",
            "X-CSRFToken": self.csrf_token,
            "Referer": self.base_url,
            "Origin": self.base_url.rstrip("/"),
            "Cookie": self._cookie_header(),
        }
        async with self.session.post(
            urljoin(self.base_url, "api/auth/login/"),
            headers=headers,
            json={
                "username": self.seed["username"],
                "password": self.password,
                "auth_mode": "local",
            },
        ) as response:
            try:
                payload = await response.json()
            except aiohttp.ContentTypeError:
                payload = {"raw_text": await response.text()}
            if response.cookies.get("sessionid"):
                self.session_cookie = str(response.cookies["sessionid"].value)
            if response.status != 200 or not payload.get("success"):
                raise SmokeFailure(f"login failed for {self.seed['username']}: HTTP {response.status} {payload}")

        auth_headers = {"Cookie": self._cookie_header()}

        async with self.session.get(urljoin(self.base_url, "api/auth/session/"), headers=auth_headers) as response:
            payload = await response.json()
            if response.status != 200 or not payload.get("authenticated"):
                raise SmokeFailure(f"session check failed for {self.seed['username']}: HTTP {response.status} {payload}")

        async with self.session.get(urljoin(self.base_url, "api/auth/ws-token/"), headers=auth_headers) as response:
            payload = await response.json()
            if response.status != 200 or not payload.get("token"):
                raise SmokeFailure(f"ws-token failed for {self.seed['username']}: HTTP {response.status} {payload}")
            self.ws_token = str(payload["token"])

        async with self.session.get(
            urljoin(self.base_url, "servers/api/frontend/bootstrap/"),
            headers=auth_headers,
        ) as response:
            payload = await response.json()
            if response.status != 200 or not payload.get("success"):
                raise SmokeFailure(f"bootstrap failed for {self.seed['username']}: HTTP {response.status} {payload}")
            server_ids = {int(item["id"]) for item in payload.get("servers", []) if "id" in item}
            if int(self.seed["server_id"]) not in server_ids:
                raise SmokeFailure(f"server {self.seed['server_id']} missing in bootstrap for {self.seed['username']}")

    async def run_terminal_session(self, session_index: int) -> float:
        started = time.perf_counter()
        ws_url = (
            f"{self.ws_base}/ws/servers/{int(self.seed['server_id'])}/terminal/?ws_token={self.ws_token}"
        )
        marker = f"TERM_OK_{self.seed['username']}_{session_index}"
        async with self.session.ws_connect(ws_url, heartbeat=20) as ws:
            await _expect_json(ws, predicate=lambda p: p.get("type") == "ready")
            await ws.send_json(
                {
                    "type": "connect",
                    "cols": 100,
                    "rows": 32,
                    "term_type": "xterm-256color",
                }
            )
            await _expect_json(
                ws,
                timeout=40,
                predicate=lambda p: p.get("type") == "status" and p.get("status") == "connected",
            )
            await ws.send_json({"type": "input", "data": f"printf '{marker}\\n'\\r"})

            deadline = time.monotonic() + 40
            seen_marker = False
            while time.monotonic() < deadline:
                payload = await _expect_json(ws, timeout=10)
                if payload.get("type") == "output" and marker in str(payload.get("data") or ""):
                    seen_marker = True
                    break
            if not seen_marker:
                raise SmokeFailure(f"terminal marker not observed for {self.seed['username']}#{session_index}")
            await ws.send_json({"type": "disconnect"})
        return time.perf_counter() - started

    async def run_pipeline(self, run_index: int) -> float:
        started = time.perf_counter()
        headers = {
            "Content-Type": "application/json",
            "X-CSRFToken": self.csrf_token,
            "Referer": self.base_url,
            "Origin": self.base_url.rstrip("/"),
            "Cookie": self._cookie_header(),
        }
        async with self.session.post(
            urljoin(self.base_url, f"api/studio/pipelines/{int(self.seed['pipeline_id'])}/run/"),
            headers=headers,
            json={"context": {"load_user": self.seed["username"], "run_index": run_index}},
        ) as response:
            payload = await response.json()
            if response.status != 202:
                raise SmokeFailure(
                    f"pipeline run failed for {self.seed['username']}: HTTP {response.status} {payload}"
                )
            run_id = int(payload["id"])

        run_detail = await _poll_run(
            self.session,
            base_url=self.base_url,
            run_id=run_id,
            headers={"Cookie": self._cookie_header()},
        )
        if str(run_detail.get("status") or "") != "completed":
            raise SmokeFailure(
                f"pipeline run {run_id} for {self.seed['username']} finished with {run_detail.get('status')}: "
                f"{run_detail.get('error') or run_detail.get('summary')}"
            )
        node_states = run_detail.get("node_states") or {}
        ssh_state = node_states.get("ssh") if isinstance(node_states, dict) else None
        output = str((ssh_state or {}).get("output") or "")
        expected = f"PIPELINE_OK {self.seed['username']} {run_index}"
        if expected not in output:
            raise SmokeFailure(f"pipeline output missing marker for {self.seed['username']}#{run_index}")
        return time.perf_counter() - started

    async def run_agent(self, run_index: int) -> float:
        started = time.perf_counter()
        headers = {
            "Content-Type": "application/json",
            "X-CSRFToken": self.csrf_token,
            "Referer": self.base_url,
            "Origin": self.base_url.rstrip("/"),
            "Cookie": self._cookie_header(),
        }
        async with self.session.post(
            urljoin(self.base_url, f"servers/api/agents/{int(self.seed['agent_id'])}/run/"),
            headers=headers,
            json={},
        ) as response:
            try:
                payload = await response.json()
            except aiohttp.ContentTypeError:
                payload = {"raw_text": await response.text()}
            if response.status != 200 or not payload.get("success"):
                raise SmokeFailure(
                    f"agent run failed for {self.seed['username']}: HTTP {response.status} {payload}"
                )
            run_id = int((payload.get("runs") or [{}])[0].get("run_id") or payload.get("run_id") or 0)
            if not run_id:
                raise SmokeFailure(f"agent run id missing for {self.seed['username']}: {payload}")

        detail_payload = await _get_agent_run_detail(
            self.session,
            base_url=self.base_url,
            run_id=run_id,
            headers={"Cookie": self._cookie_header()},
        )
        run_detail = detail_payload.get("run") or {}
        if str(run_detail.get("status") or "") != "completed":
            raise SmokeFailure(
                f"agent run {run_id} for {self.seed['username']} finished with {run_detail.get('status')}: "
                f"{run_detail.get('ai_analysis') or run_detail.get('final_report')}"
            )
        outputs = run_detail.get("commands_output") or []
        combined_output = "\n".join(
            f"{item.get('stdout', '')}\n{item.get('stderr', '')}" for item in outputs if isinstance(item, dict)
        )
        expected = f"AGENT_OK {self.seed['username']}"
        if expected not in combined_output:
            raise SmokeFailure(f"agent output missing marker for {self.seed['username']}#{run_index}")
        return time.perf_counter() - started


async def _run_user(
    *,
    base_url: str,
    seed: dict[str, Any],
    shared_password: str,
    terminal_sessions_per_user: int,
    pipeline_runs_per_user: int,
    agent_runs_per_user: int,
) -> dict[str, Any]:
    user = SmokeUserSession(base_url=base_url, seed=seed, shared_password=shared_password)
    try:
        await user.login()
        terminal_tasks = [
            asyncio.create_task(user.run_terminal_session(index))
            for index in range(1, terminal_sessions_per_user + 1)
        ]
        pipeline_tasks = [
            asyncio.create_task(user.run_pipeline(index))
            for index in range(1, pipeline_runs_per_user + 1)
        ]
        agent_tasks = [
            asyncio.create_task(user.run_agent(index))
            for index in range(1, agent_runs_per_user + 1)
        ]
        terminal_latencies = await asyncio.gather(*terminal_tasks)
        pipeline_latencies = await asyncio.gather(*pipeline_tasks)
        agent_latencies = await asyncio.gather(*agent_tasks)
        return {
            "username": seed["username"],
            "terminal_sessions": len(terminal_latencies),
            "pipeline_runs": len(pipeline_latencies),
            "agent_runs": len(agent_latencies),
            "terminal_latencies": terminal_latencies,
            "pipeline_latencies": pipeline_latencies,
            "agent_latencies": agent_latencies,
        }
    finally:
        await user.close()


def _flatten(items: list[dict[str, Any]], key: str) -> list[float]:
    out: list[float] = []
    for item in items:
        out.extend(float(x) for x in item.get(key, []))
    return out


async def _main_async(args) -> int:
    seed_data = json.loads(Path(args.seed_file).read_text(encoding="utf-8"))
    users = list(seed_data.get("users") or [])
    selected_users = users[: args.users] if args.users else users
    if not selected_users:
        raise SmokeFailure("seed file contains no users")

    started = time.perf_counter()
    results = await asyncio.gather(
        *[
            _run_user(
                base_url=args.base_url,
                seed=user_seed,
                shared_password=str(seed_data.get("password") or args.default_password),
                terminal_sessions_per_user=args.terminal_sessions_per_user,
                pipeline_runs_per_user=args.pipeline_runs_per_user,
                agent_runs_per_user=args.agent_runs_per_user,
            )
            for user_seed in selected_users
        ]
    )
    elapsed = time.perf_counter() - started

    terminal_latencies = _flatten(results, "terminal_latencies")
    pipeline_latencies = _flatten(results, "pipeline_latencies")
    agent_latencies = _flatten(results, "agent_latencies")
    summary = {
        "users": len(results),
        "terminal_sessions_total": len(terminal_latencies),
        "pipeline_runs_total": len(pipeline_latencies),
        "agent_runs_total": len(agent_latencies),
        "elapsed_seconds": round(elapsed, 3),
        "terminal_latency_avg": round(statistics.mean(terminal_latencies), 3) if terminal_latencies else 0.0,
        "terminal_latency_max": round(max(terminal_latencies), 3) if terminal_latencies else 0.0,
        "pipeline_latency_avg": round(statistics.mean(pipeline_latencies), 3) if pipeline_latencies else 0.0,
        "pipeline_latency_max": round(max(pipeline_latencies), 3) if pipeline_latencies else 0.0,
        "agent_latency_avg": round(statistics.mean(agent_latencies), 3) if agent_latencies else 0.0,
        "agent_latency_max": round(max(agent_latencies), 3) if agent_latencies else 0.0,
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run isolated multi-user runtime smoke against a live WEU stack.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--seed-file", required=True)
    parser.add_argument("--users", type=int, default=4)
    parser.add_argument("--terminal-sessions-per-user", type=int, default=2)
    parser.add_argument("--pipeline-runs-per-user", type=int, default=2)
    parser.add_argument("--agent-runs-per-user", type=int, default=0)
    parser.add_argument("--default-password", default="SmokePass123!")
    args = parser.parse_args()

    try:
        return asyncio.run(_main_async(args))
    except Exception as exc:
        print(f"SMOKE_LOAD_FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
