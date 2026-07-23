"""Live Ansible output parser and subprocess streaming.

Extracted from ansible_engine.py to keep modules under the size limit.
Re-exported from servers.services.ansible_engine for backward compatibility.
"""

from __future__ import annotations

import contextlib
import logging
import queue
import re
import subprocess
import threading
import time
from collections.abc import Callable
from typing import Any

from servers.services.ansible_setup import _safe_host_name

logger = logging.getLogger(__name__)

_STATUS_SEVERITY = {"pending": 0, "skipped": 1, "success": 2, "changed": 2, "error": 3}


class AnsibleLiveParser:
    """Incremental parser for the default Ansible stdout callback.

    Feed lines as they stream from ansible-playbook; exposes a progress
    snapshot (current play/task, counters) and per-host task results that can
    be persisted while the run is still active.
    """

    _RE_PLAY = re.compile(r"^PLAY \[(?P<name>.*)\] \*+\s*$")
    _RE_TASK = re.compile(r"^(?:TASK|RUNNING HANDLER) \[(?P<name>.*)\] \*+\s*$")
    _RE_RESULT = re.compile(
        r"^(?P<verb>ok|changed|failed|fatal|skipping|unreachable): \[(?P<host>[^\]\s]+)\](?P<rest>.*)$"
    )
    _RE_RECAP_HOST = re.compile(
        r"^(?P<host>\S+)\s*:\s*ok=(?P<ok>\d+)\s+changed=(?P<changed>\d+)\s+"
        r"unreachable=(?P<unreach>\d+)\s+failed=(?P<failed>\d+)"
    )

    def __init__(self, servers: list[Any], *, tasks_total: int = 0):
        self._servers = servers
        self._by_alias = {_safe_host_name(getattr(s, "name", ""), int(s.id)): s for s in servers}
        self._by_host = {str(getattr(s, "host", "")): s for s in servers}
        self.tasks_total = int(tasks_total or 0)
        self.current_play = ""
        self.current_task = ""
        self.task_seq = 0
        self.play_count = 0
        self.counts = {"ok": 0, "changed": 0, "failed": 0, "skipped": 0, "unreachable": 0}
        self.in_recap = False
        self.recap: dict[str, dict[str, int]] = {}
        # host_key -> {"tasks": [{"seq", "name", "status", "note"}]}
        self._hosts: dict[str, dict[str, Any]] = {}

    def feed(self, raw_line: str) -> None:
        line = (raw_line or "").rstrip()
        if not line:
            return
        m = self._RE_PLAY.match(line)
        if m:
            self.current_play = m.group("name")
            self.play_count += 1
            self.in_recap = False
            return
        if line.startswith("PLAY RECAP"):
            self.in_recap = True
            return
        m = self._RE_TASK.match(line)
        if m:
            self.current_task = m.group("name")
            self.task_seq += 1
            self.in_recap = False
            return
        if self.in_recap:
            m = self._RE_RECAP_HOST.match(line)
            if m:
                self.recap[m.group("host")] = {
                    "ok": int(m.group("ok")),
                    "changed": int(m.group("changed")),
                    "unreachable": int(m.group("unreach")),
                    "failed": int(m.group("failed")),
                }
            return
        m = self._RE_RESULT.match(line)
        if not m:
            return
        verb = m.group("verb")
        host_key = m.group("host")
        rest = m.group("rest") or ""
        unreachable = verb == "unreachable" or (verb == "fatal" and "UNREACHABLE" in rest.upper())
        if verb in ("ok",):
            status = "success"
        elif verb == "changed":
            status = "success"
            self.counts["changed"] += 1
        elif verb == "skipping":
            status = "skipped"
        else:  # failed / fatal / unreachable
            status = "error"
        if status == "success":
            self.counts["ok"] += 1
        elif status == "skipped":
            self.counts["skipped"] += 1
        elif unreachable:
            self.counts["unreachable"] += 1
        else:
            self.counts["failed"] += 1

        note = ""
        if status == "error":
            note = rest.lstrip(" :=>").strip()[:4000]
        state = self._hosts.setdefault(host_key, {"tasks": []})
        tasks: list[dict[str, Any]] = state["tasks"]
        # Item results (`=> (item=...)`) repeat per task+host — merge by task_seq keeping the worst status
        if tasks and tasks[-1]["seq"] == self.task_seq:
            entry = tasks[-1]
            if _STATUS_SEVERITY.get(status, 0) > _STATUS_SEVERITY.get(entry["status"], 0):
                entry["status"] = status
                if note:
                    entry["note"] = note
        else:
            tasks.append(
                {
                    "seq": self.task_seq,
                    "name": self.current_task or f"Task {self.task_seq}",
                    "status": status,
                    "note": note,
                }
            )

    def snapshot(self) -> dict[str, Any]:
        return {
            "engine": "ansible",
            "play": self.current_play,
            "plays": self.play_count,
            "task": self.current_task,
            "task_number": self.task_seq,
            "tasks_total": self.tasks_total or None,
            "counts": dict(self.counts),
            "hosts_seen": len(self._hosts),
            "hosts_total": len(self._servers),
            "recap_seen": bool(self.recap),
        }

    def build_host_results(self, *, final: bool = False) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen_ids: set[int] = set()
        for host_key, state in self._hosts.items():
            server = self._by_alias.get(host_key) or self._by_host.get(host_key)
            sid = int(server.id) if server is not None else 0
            if sid:
                seen_ids.add(sid)
            task_results = [
                {
                    "task_id": f"{host_key}_{t['seq']}",
                    "command": t["name"],
                    "description": t["name"],
                    "status": t["status"],
                    "output": t.get("note") or "",
                    "exit_code": 1 if t["status"] == "error" else 0,
                }
                for t in state["tasks"]
            ]
            recap = self.recap.get(host_key)
            has_error = any(t["status"] == "error" for t in state["tasks"])
            has_success = any(t["status"] == "success" for t in state["tasks"])
            if recap:
                if recap["failed"] or recap["unreachable"]:
                    status = "partial" if (recap["ok"] and not recap["unreachable"]) else "error"
                elif recap["ok"] or recap["changed"]:
                    status = "success"
                else:
                    status = "skipped"
            elif final:
                status = "partial" if (has_error and has_success) else ("error" if has_error else "success")
            else:
                status = "error" if has_error else "running"
            results.append(
                {
                    "server_id": sid,
                    "server_name": getattr(server, "name", host_key) if server else host_key,
                    "host": getattr(server, "host", host_key) if server else host_key,
                    "status": status,
                    "task_results": task_results,
                }
            )
        for s in self._servers:
            if int(s.id) not in seen_ids:
                results.append(
                    {
                        "server_id": int(s.id),
                        "server_name": s.name,
                        "host": s.host,
                        "status": "skipped" if final else "pending",
                        "task_results": [],
                    }
                )
        return results

    @property
    def has_events(self) -> bool:
        return any(state["tasks"] for state in self._hosts.values())


def _terminate_process(proc: subprocess.Popen) -> None:
    with contextlib.suppress(Exception):
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        with contextlib.suppress(Exception):
            proc.kill()


def _stream_command(
    cmd: list[str],
    *,
    cwd: str | None,
    env: dict[str, str] | None,
    timeout: int,
    cancel_check: Callable[[], bool] | None = None,
    on_line: Callable[[str], None] | None = None,
) -> tuple[int, str, bool, bool]:
    """Run a command streaming merged stdout/stderr line by line.

    Returns (exit_code, combined_output, cancelled, timed_out). Unlike
    subprocess.run this checks cancel_check while the process runs and kills
    the process on cancel or timeout.
    """
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    lines_q: queue.Queue[str | None] = queue.Queue()

    def _reader() -> None:
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                lines_q.put(line)
        except Exception:
            pass
        finally:
            lines_q.put(None)

    threading.Thread(target=_reader, name="ansible-stream-reader", daemon=True).start()

    lines: list[str] = []
    cancelled = False
    timed_out = False
    killed = False
    deadline = time.monotonic() + max(30, int(timeout))
    last_cancel_probe = 0.0

    while True:
        try:
            item = lines_q.get(timeout=0.5)
        except queue.Empty:
            item = ""
        if item is None:
            break
        if item:
            line = item.rstrip("\r\n")
            lines.append(line)
            if on_line:
                try:
                    on_line(line)
                except Exception:
                    logger.debug("ansible on_line callback failed", exc_info=True)
        if killed:
            continue
        now = time.monotonic()
        if cancel_check and now - last_cancel_probe >= 1.0:
            last_cancel_probe = now
            try:
                if cancel_check():
                    cancelled = True
            except Exception:
                pass
        if cancelled or now > deadline:
            timed_out = not cancelled and now > deadline
            killed = True
            _terminate_process(proc)

    try:
        exit_code = proc.wait(timeout=30)
    except Exception:
        exit_code = 1
    if cancelled:
        exit_code = 130
    elif timed_out:
        exit_code = 124
    return exit_code, "\n".join(lines), cancelled, timed_out
