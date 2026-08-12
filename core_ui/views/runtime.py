"""
Shared runtime singletons for legacy Core UI views.

These helpers are intentionally framework-light: views can import them without
owning orchestrator/RAG lifecycle details.
"""

import asyncio
import warnings

from dotenv import load_dotenv

from app.core.model_config import model_manager

load_dotenv()

try:
    from app.core.unified_orchestrator import UnifiedOrchestrator
except Exception:
    UnifiedOrchestrator = None

try:
    from app.rag.engine import RAGEngine
except Exception:
    RAGEngine = None


_unified_orchestrator = None
_orchestrator_lock = asyncio.Lock()
_rag_engine = None


class RagBackendNotConfiguredError(RuntimeError):
    pass


def _init_unified_orchestrator_sync():
    """Initialize the unified orchestrator in a worker thread."""
    if UnifiedOrchestrator is None:
        raise RuntimeError("UnifiedOrchestrator is not available in mini build")
    model_manager.load_config()
    return UnifiedOrchestrator()


async def get_unified_orchestrator():
    """Get or create the shared unified orchestrator instance."""
    global _unified_orchestrator
    async with _orchestrator_lock:
        if _unified_orchestrator is None:
            _unified_orchestrator = await asyncio.to_thread(_init_unified_orchestrator_sync)
            await _unified_orchestrator.initialize()
    return _unified_orchestrator


async def get_orchestrator():
    """
    Deprecated compatibility alias for legacy callers.

    New code should call get_unified_orchestrator().
    """
    warnings.warn(
        "get_orchestrator() is deprecated. Use get_unified_orchestrator() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return await get_unified_orchestrator()


def get_rag_engine():
    """Get or create the shared RAG engine instance."""
    global _rag_engine
    if _rag_engine is None:
        if RAGEngine is None:
            raise RagBackendNotConfiguredError("RAG is disabled: configure a separate embedding backend first")
        _rag_engine = RAGEngine()
    return _rag_engine


def rag_backend_is_configured() -> bool:
    if RAGEngine is None:
        return False
    try:
        return bool(get_rag_engine().available)
    except Exception:
        return False


def get_cached_rag_service_status() -> str:
    """
    Return RAG health without forcing heavy initialization.

    Historically the health endpoint reports RAG as ok until the cached engine
    proves unavailable, so this keeps that lightweight behavior.
    """
    try:
        if _rag_engine is not None:
            return "ok" if _rag_engine.available else "unavailable"
        return "disabled" if RAGEngine is None else "unknown"
    except Exception:
        return "unavailable"
