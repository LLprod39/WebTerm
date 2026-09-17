#!/usr/bin/env python3
"""Local stub for Cursor `agent` CLI (dev only)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _home() -> Path:
    return Path(os.environ.get("HOME") or "/credentials/cursor")


def _marker() -> Path:
    return _home() / ".cursor" / "local-stub-auth"


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "login":
        print(
            "Open https://authenticator.cursor.sh/loginDeepControl?challenge=local-dev-stub to continue",
            flush=True,
        )
        marker = _marker()
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("local-stub\n", encoding="utf-8")
        return 0
    if cmd == "status":
        if _marker().is_file():
            print("Logged in", flush=True)
            return 0
        print("Not logged in", flush=True)
        return 1
    print(
        json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "local cursor stub response"}]},
            },
            separators=(",", ":"),
        ),
        flush=True,
    )
    print(
        json.dumps({"type": "result", "subtype": "success", "session_id": "local-stub"}, separators=(",", ":")),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
