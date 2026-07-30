"""Compatibility alias for :mod:`studio.pipeline.pipeline_agent_runtime`."""

import sys as _sys

from studio.pipeline import pipeline_agent_runtime as _implementation

_sys.modules[__name__] = _implementation
