"""Compatibility alias for :mod:`studio.mcp.mcp_tool_runtime`."""

import sys as _sys

from studio.mcp import mcp_tool_runtime as _implementation

_sys.modules[__name__] = _implementation
