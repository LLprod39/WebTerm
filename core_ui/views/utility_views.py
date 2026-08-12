"""
Utility endpoints for disk usage, legacy agents, and RAG uploads.
"""

import json
import os
import uuid
from contextlib import suppress
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from core_ui.api_errors import internal_error_response
from core_ui.decorators import async_login_required, async_require_feature, require_feature
from core_ui.views.runtime import get_rag_engine, rag_backend_is_configured

try:
    from app.utils.file_processor import FileProcessor
except Exception:
    FileProcessor = None

try:
    from app.utils.disk_usage import get_disk_usage_report
except Exception:
    get_disk_usage_report = None

try:
    from app.agents.manager import get_agent_manager
except Exception:
    get_agent_manager = None


def _format_bytes(size: int) -> str:
    """Format bytes as a human-readable value."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


@login_required
@require_feature("settings")
@require_GET
def api_disk_usage(request):
    """Return disk usage for runtime-relevant paths."""
    try:
        if get_disk_usage_report is None:
            return JsonResponse({"paths": [], "error": "Disk usage utility is not available"}, status=500)
        report = get_disk_usage_report(
            include_root=True,
            media_root=getattr(settings, "MEDIA_ROOT", None),
            uploaded_files_dir=getattr(settings, "UPLOADED_FILES_DIR", None),
            agent_projects_dir=getattr(settings, "AGENT_PROJECTS_DIR", None),
            base_dir=getattr(settings, "BASE_DIR", None),
        )
        for entry in report:
            if "error" in entry:
                continue
            total = entry.get("total")
            used = entry.get("used")
            free = entry.get("free")
            if total is not None:
                entry["total_human"] = _format_bytes(total)
            if used is not None:
                entry["used_human"] = _format_bytes(used)
            if free is not None:
                entry["free_human"] = _format_bytes(free)
        return JsonResponse({"paths": report})
    except Exception as exc:
        return internal_error_response(request, exc)


@login_required
@require_feature("agents")
def api_agents_list(request):
    """Get list of available legacy agents."""
    try:
        if get_agent_manager is None:
            return JsonResponse({"error": "Agent manager is not available"}, status=500)
        agent_manager = get_agent_manager()
        agents = agent_manager.list_agents()
        return JsonResponse({"agents": agents})
    except Exception as exc:
        return internal_error_response(request, exc)


@async_login_required
@async_require_feature("agents")
@require_http_methods(["POST"])
async def api_agent_execute(request):
    """Execute a legacy agent with a task."""
    try:
        if get_agent_manager is None:
            return JsonResponse({"error": "Agent manager is not available"}, status=500)
        data = json.loads(request.body)
        agent_name = data.get("agent_name")
        task = data.get("task")
        context = data.get("context", {})

        if not agent_name or not task:
            return JsonResponse({"error": "agent_name and task are required"}, status=400)

        agent_manager = get_agent_manager()
        result = await agent_manager.execute_agent(agent_name, task, context)
        return JsonResponse(result)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as exc:
        return internal_error_response(request, exc)


@login_required
@require_feature("knowledge_base")
@require_http_methods(["POST"])
def api_upload_file(request):
    """Upload a file and add its extracted text to RAG."""
    try:
        if not rag_backend_is_configured():
            return JsonResponse(
                {
                    "success": False,
                    "error": "RAG is disabled: configure a separate embedding backend first",
                    "code": "rag_embedding_backend_not_configured",
                },
                status=409,
            )
        if FileProcessor is None:
            return JsonResponse({"error": "File processor is not available"}, status=500)
        if "file" not in request.FILES:
            return JsonResponse({"error": "No file provided"}, status=400)

        uploaded_file = request.FILES["file"]
        filename = uploaded_file.name
        if not FileProcessor.is_supported(filename):
            supported = ", ".join(FileProcessor.SUPPORTED_EXTENSIONS.keys())
            return JsonResponse({"error": f"Unsupported file type. Supported: {supported}"}, status=400)

        file_ext = Path(filename).suffix
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = settings.UPLOADED_FILES_DIR / unique_filename
        with open(file_path, "wb") as file_obj:
            for chunk in uploaded_file.chunks():
                file_obj.write(chunk)

        result = FileProcessor.process_file(str(file_path), filename)
        if result["error"]:
            with suppress(Exception):
                os.remove(file_path)
            return JsonResponse({"error": result["error"]}, status=400)

        rag = get_rag_engine()
        if not rag.available:
            return JsonResponse(
                {"success": False, "error": "RAG embedding backend became unavailable"},
                status=409,
            )
        if result["text"]:
            doc_id = rag.add_text(result["text"], source=f"upload:{filename}", user_id=request.user.id)
            result["metadata"]["rag_doc_id"] = doc_id

        return JsonResponse(
            {
                "success": True,
                "filename": filename,
                "text_preview": result["text"][:500] + "..." if len(result["text"]) > 500 else result["text"],
                "text_length": len(result["text"]),
                "metadata": result["metadata"],
            }
        )
    except Exception as exc:
        return internal_error_response(request, exc)
