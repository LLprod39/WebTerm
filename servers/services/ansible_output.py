"""Ansible output parsing helpers (PLAY RECAP + JSON callback).

Extracted from ansible_engine.py to keep modules under the size limit.
Re-exported from servers.services.ansible_engine for backward compatibility.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from servers.services.ansible_setup import _safe_host_name


def shlex_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _to_wsl_path(path: Path) -> str:
    resolved = str(path.resolve())
    # C:\foo\bar -> /mnt/c/foo/bar
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", resolved)
    if not m:
        return resolved.replace("\\", "/")
    drive = m.group(1).lower()
    rest = m.group(2).replace("\\", "/")
    return f"/mnt/{drive}/{rest}"


def parse_play_recap(text: str, *, servers: list[Any]) -> list[dict[str, Any]]:
    """Parse classic Ansible PLAY RECAP into host_results.

    Example line:
      app-01  : ok=3    changed=1    unreachable=0    failed=0    skipped=0
    """
    if not text:
        return []
    recap_idx = text.upper().rfind("PLAY RECAP")
    if recap_idx < 0:
        return []
    section = text[recap_idx:]
    pattern = re.compile(
        r"^(?P<host>\S+)\s*:\s*"
        r"ok=(?P<ok>\d+)\s+"
        r"changed=(?P<changed>\d+)\s+"
        r"unreachable=(?P<unreach>\d+)\s+"
        r"failed=(?P<failed>\d+)",
        re.MULTILINE,
    )
    by_alias = {_safe_host_name(s.name, s.id): s for s in servers}
    by_host = {str(s.host): s for s in servers}
    results: list[dict[str, Any]] = []
    found: set[int] = set()

    for match in pattern.finditer(section):
        host_key = match.group("host")
        if host_key.lower() in ("play", "recap"):
            continue
        ok_n = int(match.group("ok"))
        failed_n = int(match.group("failed"))
        unreach_n = int(match.group("unreach"))
        changed_n = int(match.group("changed"))
        if unreach_n or failed_n:
            status = "error"
        elif ok_n or changed_n:
            status = "success"
        else:
            status = "skipped"
        server = by_alias.get(host_key) or by_host.get(host_key)
        sid = int(server.id) if server is not None else 0
        if sid:
            found.add(sid)
        output = f"PLAY RECAP {host_key}: ok={ok_n} changed={changed_n} unreachable={unreach_n} failed={failed_n}"
        results.append(
            {
                "server_id": sid,
                "server_name": getattr(server, "name", host_key) if server else host_key,
                "host": getattr(server, "host", host_key) if server else host_key,
                "status": status,
                "task_results": [
                    {
                        "task_id": f"recap_{host_key}",
                        "command": "ansible-playbook",
                        "description": "PLAY RECAP",
                        "status": "error" if status == "error" else "success",
                        "output": output,
                        "exit_code": 1 if status == "error" else 0,
                    }
                ],
            }
        )

    # Include full log on first result for context
    if results:
        log_snip = text[-12_000:]
        results[0]["task_results"].append(
            {
                "task_id": "ansible_full_log",
                "command": "ansible-playbook",
                "description": "Ansible log (tail)",
                "status": results[0]["status"] if results[0]["status"] != "partial" else "success",
                "output": log_snip,
                "exit_code": None,
            }
        )

    for s in servers:
        if s.id not in found:
            results.append(
                {
                    "server_id": s.id,
                    "server_name": s.name,
                    "host": s.host,
                    "status": "skipped",
                    "task_results": [
                        {
                            "task_id": f"missing_{s.id}",
                            "command": "ansible",
                            "description": "Not in PLAY RECAP",
                            "status": "skipped",
                            "output": "Host did not appear in PLAY RECAP",
                            "exit_code": None,
                        }
                    ],
                }
            )
    return results


def parse_ansible_json_output(stdout: str, *, servers: list[Any]) -> list[dict[str, Any]]:
    """Parse ansible json callback stdout into WebTerm host_results."""
    text = (stdout or "").strip()
    if not text:
        return []

    # Callback may print non-json noise; find last JSON object
    data = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON blob
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                data = None
    if not isinstance(data, dict):
        return []

    plays = data.get("plays") or []
    # Map inventory hostname -> server
    by_alias: dict[str, Any] = {}
    by_host: dict[str, Any] = {}
    for s in servers:
        by_alias[_safe_host_name(s.name, s.id)] = s
        by_host[str(s.host)] = s

    # Collect per-host tasks
    host_tasks: dict[str, list[dict[str, Any]]] = {}
    host_status: dict[str, str] = {}

    for play in plays:
        for task in play.get("tasks") or []:
            task_name = ""
            if isinstance(task.get("task"), dict):
                task_name = str(task["task"].get("name") or "")
            hosts_map = task.get("hosts") or {}
            if not isinstance(hosts_map, dict):
                continue
            for host_key, result in hosts_map.items():
                if not isinstance(result, dict):
                    continue
                tr_status = "success"
                if result.get("failed") or result.get("unreachable"):
                    tr_status = "error"
                    host_status[host_key] = "error"
                elif result.get("skipped"):
                    tr_status = "skipped"
                else:
                    host_status.setdefault(host_key, "success")

                stdout_bits = []
                for key in ("stdout", "stderr", "msg", "reason"):
                    val = result.get(key)
                    if val:
                        stdout_bits.append(str(val))
                if result.get("diff"):
                    stdout_bits.append(json.dumps(result.get("diff"), ensure_ascii=False)[:4000])
                output = "\n".join(stdout_bits).strip()
                rc = result.get("rc")
                if rc is None:
                    rc = 1 if tr_status == "error" else 0

                host_tasks.setdefault(host_key, []).append(
                    {
                        "task_id": f"{host_key}_{len(host_tasks.get(host_key, []))}",
                        "command": task_name or "ansible task",
                        "description": task_name,
                        "status": tr_status,
                        "output": output[:50_000],
                        "exit_code": rc,
                    }
                )

    # stats section
    stats = data.get("stats") or {}
    if isinstance(stats, dict):
        for host_key, st in stats.items():
            if not isinstance(st, dict):
                continue
            if st.get("unreachable") or st.get("failures"):
                host_status[host_key] = "error"
            elif host_key not in host_status:
                host_status[host_key] = "success"

    results: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for host_key, tasks in host_tasks.items():
        server = by_alias.get(host_key) or by_host.get(host_key)
        sid = int(server.id) if server is not None else 0
        if sid:
            seen_ids.add(sid)
        status = host_status.get(host_key, "success")
        if any(t["status"] == "error" for t in tasks) and any(t["status"] == "success" for t in tasks):
            status = "partial"
        elif any(t["status"] == "error" for t in tasks):
            status = "error"
        results.append(
            {
                "server_id": sid,
                "server_name": getattr(server, "name", host_key) if server else host_key,
                "host": getattr(server, "host", host_key) if server else host_key,
                "status": status,
                "task_results": tasks,
            }
        )

    # Ensure all target servers appear
    for s in servers:
        if s.id not in seen_ids:
            results.append(
                {
                    "server_id": s.id,
                    "server_name": s.name,
                    "host": s.host,
                    "status": "skipped",
                    "task_results": [
                        {
                            "task_id": f"missing_{s.id}",
                            "command": "ansible",
                            "description": "No task results for host",
                            "status": "skipped",
                            "output": "Host did not appear in Ansible JSON output",
                            "exit_code": None,
                        }
                    ],
                }
            )

    return results


def _summarize_hosts(host_results: list[dict[str, Any]]) -> dict[str, Any]:
    hosts_total = len(host_results)
    hosts_ok = sum(1 for h in host_results if h.get("status") == "success")
    hosts_failed = sum(1 for h in host_results if h.get("status") in ("error", "failed"))
    hosts_partial = sum(1 for h in host_results if h.get("status") == "partial")
    tasks_ok = tasks_failed = tasks_skipped = 0
    for h in host_results:
        for t in h.get("task_results") or []:
            if t.get("status") == "success":
                tasks_ok += 1
            elif t.get("status") == "error":
                tasks_failed += 1
            elif t.get("status") == "skipped":
                tasks_skipped += 1
    return {
        "hosts_total": hosts_total,
        "hosts_ok": hosts_ok,
        "hosts_failed": hosts_failed,
        "hosts_partial": hosts_partial,
        "tasks_ok": tasks_ok,
        "tasks_failed": tasks_failed,
        "tasks_skipped": tasks_skipped,
        "engine": "ansible",
    }
