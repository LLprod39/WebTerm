"""Compatibility alias for :mod:`studio.pipeline.pipeline_secrets`."""

import sys as _sys

from studio.pipeline import pipeline_secrets as _implementation

_sys.modules[__name__] = _implementation
