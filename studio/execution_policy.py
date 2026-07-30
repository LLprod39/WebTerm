"""Compatibility alias for :mod:`studio.policy.execution_policy`."""

import sys as _sys

from studio.policy import execution_policy as _implementation

_sys.modules[__name__] = _implementation
