"""Single-shot boundary for an isolated backend plugin package."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

INPUT_LIMIT = 4 * 1024 * 1024


def _bounded(value: Any, limit: int) -> str:
    text = str(value or "")
    return text if len(text.encode("utf-8")) <= limit else text[:limit]


def _run(payload: dict[str, Any]) -> dict[str, Any]:
    timeout = max(1, min(int(payload.get("timeout_seconds") or 10), 300))
    output_limit = max(1024, min(int(payload.get("output_limit_bytes") or 262144), 1024 * 1024))
    package_bytes = base64.b64decode(str(payload.get("package_b64") or ""), validate=True)
    if len(package_bytes) > 2 * 1024 * 1024:
        raise ValueError("Plugin package exceeds the 2 MiB runner limit.")
    with tempfile.TemporaryDirectory(prefix="plugin-job-") as temp_dir:
        root = Path(temp_dir)
        package_path = root / "package.wtp"
        input_path = root / "input.json"
        output_path = root / "output.json"
        package_path.write_bytes(package_bytes)
        input_path.write_text(json.dumps(payload.get("payload") or {}, ensure_ascii=False), encoding="utf-8")
        command = [
            sys.executable,
            "-I",
            "/opt/webterm/sandbox_worker.py",
            "--package",
            str(package_path),
            "--executor-ref",
            str(payload.get("executor_ref") or ""),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
        if bool(payload.get("smoke_only")):
            command.append("--smoke-only")
        completed = subprocess.run(command, capture_output=True, check=False, timeout=timeout)
        if completed.returncode != 0 or not output_path.is_file():
            detail = completed.stderr.decode("utf-8", errors="replace") or "Plugin runner failed."
            return {"success": False, "error": _bounded(detail, 2000)}
        if output_path.stat().st_size > output_limit:
            return {"success": False, "error": "Plugin output exceeded the configured limit."}
        result = json.loads(output_path.read_text(encoding="utf-8"))
        return result if isinstance(result, dict) else {"success": False, "error": "Plugin output was not an object."}


def main() -> int:
    raw = sys.stdin.buffer.read(INPUT_LIMIT + 1)
    if len(raw) > INPUT_LIMIT:
        print(json.dumps({"success": False, "error": "Runner input limit exceeded."}))
        return 2
    try:
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("schema") != "webterm.plugin-backend.v1":
            raise ValueError("Unsupported plugin runner request schema.")
        result = _run(payload)
    except Exception as exc:  # noqa: BLE001 - isolated process boundary
        result = {"success": False, "error": _bounded(exc, 2000)}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
