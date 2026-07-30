"""Compatibility entrypoint for the relocated Studio demo MCP server."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:  # pragma: no cover - exercised by subprocess tests.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from studio.mcp.demo_mcp_server import main

if __name__ == "__main__":
    raise SystemExit(main())
