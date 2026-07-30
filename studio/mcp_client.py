"""Compatibility alias for :mod:`studio.mcp.mcp_client`."""

import sys as _sys

from studio.mcp import mcp_client as _implementation

_sys.modules[__name__] = _implementation
