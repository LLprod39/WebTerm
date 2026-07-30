"""Compatibility alias for :mod:`servers.playbooks.dispatch`."""

import sys as _sys

from servers.playbooks import dispatch as _implementation

_sys.modules[__name__] = _implementation
