"""Compatibility alias for :mod:`studio.pipeline.pipeline_validation`."""

import sys as _sys

from studio.pipeline import pipeline_validation as _implementation

_sys.modules[__name__] = _implementation
