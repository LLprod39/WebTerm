"""
Legacy Django-rendered page views kept for compatibility with old routes.
"""

from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET
from loguru import logger

from app.core.model_config import model_manager
from core_ui.decorators import require_feature
from core_ui.middleware import get_template_name
from core_ui.views.runtime import get_rag_engine, rag_backend_is_configured


def welcome_view(request):
    """Public landing page: pitch, gallery, features, trust, CTA."""
    return render(request, "welcome.html")


def docs_ui_guide_view(request):
    """Documentation: UI guide."""
    return render(request, "docs_ui_guide.html")


@login_required
def mobile_app_view(request):
    """Mobile PWA - compact app shell for phones."""
    return render(request, "mobile_app.html")


_ALLOWED_LANDING_VIDEOS = {
    "agent.mp4",
    "mcp.mp4",
    "server.mp4",
    "task.mp4",
    "agent.mkv",
    "mcp.mkv",
    "server.mkv",
    "task.mkv",
}


@require_GET
def serve_landing_video(request, filename):
    """Serve landing videos without depending on staticfiles."""
    if filename not in _ALLOWED_LANDING_VIDEOS:
        raise Http404
    video_dir = (Path(settings.BASE_DIR) / "core_ui" / "static" / "landing" / "videos").resolve()
    filepath = (video_dir / filename).resolve()
    try:
        filepath.relative_to(video_dir)
    except ValueError:
        raise Http404 from None
    if not filepath.is_file():
        raise Http404
    content_type = "video/mp4" if filename.endswith(".mp4") else "video/x-matroska"
    return FileResponse(open(filepath, "rb"), content_type=content_type, as_attachment=False)


@login_required
@require_feature("chat", redirect_on_forbidden=True)
def chat_view(request):
    """Main chat interface."""
    default_provider = model_manager.config.default_provider
    rag = get_rag_engine() if rag_backend_is_configured() else None
    context = {
        "default_provider": default_provider,
        "is_auto_default": default_provider == "auto",
        "is_gemini_default": default_provider == "gemini",
        "is_grok_default": default_provider == "grok",
        "rag_available": bool(rag and rag.available),
        "rag_build": getattr(rag, "rag_build", "disabled"),
    }

    task_id = request.GET.get("task_id")
    if task_id:
        try:
            from tasks.models import Task

            task = Task.objects.get(id=task_id)
            initial_prompt = (
                f"I need you to execute this task: '{task.title}'.\n\n"
                f"Description:\n{task.description}\n\n"
                "Please analyze it and start working on it."
            )
            context["initial_prompt"] = initial_prompt.replace("\n", "\\n").replace("'", "\\'")
        except Exception as exc:
            logger.warning(f"Failed to prefill task prompt for task_id={task_id}: {exc}")

    template = get_template_name(request, "chat.html")
    return render(request, template, context)


index = chat_view


@login_required
@require_feature("orchestrator", redirect_on_forbidden=True)
def orchestrator_view(request):
    """Orchestrator dashboard - shows agent workflow."""
    template = get_template_name(request, "orchestrator.html")
    return render(request, template, {"tool_count": 0})


@login_required
@require_feature("agents", redirect_on_forbidden=True)
def monitor_view(request):
    """AI Monitor - unified monitoring dashboard for agent and workflow runs."""
    return render(request, "monitor.html", {})


@login_required
@require_feature("knowledge_base", redirect_on_forbidden=True)
def knowledge_base_view(request):
    """Knowledge Base (RAG) management - optimized for fast loading."""
    rag = get_rag_engine() if rag_backend_is_configured() else None
    rag_type = (
        "Qdrant"
        if (rag is not None and hasattr(rag, "use_qdrant") and rag.use_qdrant)
        else ("InMemory" if rag is not None and rag.available else "disabled")
    )
    context = {
        "documents": [],
        "doc_count": 0,
        "rag_available": bool(rag and rag.available),
        "rag_type": rag_type,
        "rag_build": getattr(rag, "rag_build", "disabled"),
    }
    template = get_template_name(request, "knowledge_base.html")
    return render(request, template, context)
