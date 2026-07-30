"""Compatibility alias for :mod:`studio.pipeline.pipeline_context`."""

import sys as _sys

from studio.pipeline import pipeline_context as _implementation

_sys.modules[__name__] = _implementation
