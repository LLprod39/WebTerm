"""Compatibility alias for :mod:`studio.mcp.mcp_security`."""

import sys as _sys

from studio.mcp import mcp_security as _implementation

_sys.modules[__name__] = _implementation
