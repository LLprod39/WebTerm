"""Compatibility alias for :mod:`servers.playbooks.worker`."""

import sys as _sys

from servers.playbooks import worker as _implementation

_sys.modules[__name__] = _implementation
