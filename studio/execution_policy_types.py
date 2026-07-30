"""Compatibility alias for :mod:`studio.policy.execution_policy_types`."""

import sys as _sys

from studio.policy import execution_policy_types as _implementation

_sys.modules[__name__] = _implementation
