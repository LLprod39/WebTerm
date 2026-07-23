"""Shared constants for terminal WebSocket consumer modules."""

from __future__ import annotations

import asyncio

_WEUAI_MARKER_PREFIX = "__WEUAI_EXIT_"

# Limit concurrent terminal-AI LLM calls to avoid provider rate limits (429)
_TERMINAL_AI_LLM_SEMAPHORE = asyncio.Semaphore(4)
