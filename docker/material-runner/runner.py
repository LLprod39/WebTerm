import json
import subprocess
import sys
import time
from pathlib import Path


def main():
    raw = sys.stdin.buffer.read(1_048_577)
    if len(raw) > 1_048_576:
        raise ValueError("input too large")
    payload = json.loads(raw.decode("utf-8"))
    if payload.get("schema") != "webterm.material-run.v1" or payload.get("language") not in {"bash", "shell", "sh"}:
        raise ValueError("unsupported request")
    content = str(payload.get("content") or "")
    args = payload.get("args") or []
    if not isinstance(args, list) or any(not isinstance(item, str) or len(item) > 512 for item in args):
        raise ValueError("invalid args")
    timeout = max(1, min(int(payload.get("timeout_seconds") or 120), 300))
    output_limit = max(1024, min(int(payload.get("output_limit") or 50_000), 200_000))
    script = Path("/work/material.sh")
    script.write_text(content, encoding="utf-8")
    script.chmod(0o500)
    started = time.monotonic()
    env = {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME": "/work",
        "TMPDIR": "/work",
        "LANG": "C.UTF-8",
    }
    try:
        result = subprocess.run(
            ["/bin/bash", "--noprofile", "--norc", str(script), *args],
            cwd="/work",
            env=env,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        stdout, stderr, code = result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, code = exc.stdout or b"", (exc.stderr or b"") + b"\nmaterial timeout", 124
    response = {
        "schema": "webterm.material-result.v1",
        "stdout": stdout.decode("utf-8", "replace")[:output_limit],
        "stderr": stderr.decode("utf-8", "replace")[:output_limit],
        "exit_status": code,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }
    sys.stdout.write(json.dumps(response, ensure_ascii=False))


try:
    main()
except Exception as exc:
    sys.stderr.write(f"material runner error: {exc}\n")
    raise SystemExit(2) from exc
