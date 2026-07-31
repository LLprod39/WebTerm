"""
Legacy web IDE views and file API.
"""

import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from loguru import logger

from core_ui.api_errors import internal_error_response
from core_ui.decorators import require_feature


def _ensure_relative_to(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("Path outside workspace") from exc


def _normalize_relative_path(path_param: str) -> str:
    normalized = (path_param or "").strip().strip("/").strip("\\")
    if ".." in normalized:
        raise ValueError("Invalid path")
    return normalized


def _resolve_ide_workspace(workspace_param: str) -> Path:
    """Resolve a workspace path inside AGENT_PROJECTS_DIR."""
    normalized = _normalize_relative_path(workspace_param)
    if not normalized:
        raise ValueError("workspace parameter is required")
    if normalized.startswith("/"):
        raise ValueError("Invalid workspace path")

    projects_dir = Path(settings.AGENT_PROJECTS_DIR)
    workspace_path = projects_dir / normalized
    _ensure_relative_to(workspace_path, projects_dir)
    return workspace_path


def _resolve_workspace_child(workspace_root: Path, path_param: str) -> Path:
    normalized = _normalize_relative_path(path_param)
    target_path = workspace_root / normalized if normalized else workspace_root
    _ensure_relative_to(target_path, workspace_root)
    return target_path


@login_required
@require_feature("orchestrator")
@require_http_methods(["GET"])
def api_ide_list_files(request):
    """Return files and directories in a workspace directory."""
    try:
        workspace_param = request.GET.get("workspace", "").strip()
        path_param = request.GET.get("path", "").strip()
        if not workspace_param:
            return JsonResponse({"error": "workspace parameter is required"}, status=400)

        try:
            workspace_root = _resolve_ide_workspace(workspace_param)
            target_path = _resolve_workspace_child(workspace_root, path_param)
        except ValueError as exc:
            status = 403 if "outside" in str(exc).lower() else 400
            return JsonResponse({"error": str(exc)}, status=status)

        if not target_path.exists():
            return JsonResponse({"error": "Path not found"}, status=404)
        if not target_path.is_dir():
            return JsonResponse({"error": "Path is not a directory"}, status=400)

        files = []
        try:
            for item in sorted(target_path.iterdir()):
                if item.name.startswith("."):
                    continue
                rel_path = item.relative_to(workspace_root)
                files.append(
                    {
                        "name": item.name,
                        "path": str(rel_path).replace("\\", "/"),
                        "type": "dir" if item.is_dir() else "file",
                    }
                )
        except PermissionError:
            return JsonResponse({"error": "Permission denied"}, status=403)
        except Exception as exc:
            logger.error(f"Error listing directory {target_path}: {exc}")
            return internal_error_response(request, exc)

        return JsonResponse({"files": files})
    except Exception as exc:
        logger.error(f"api_ide_list_files error: {exc}")
        return internal_error_response(request, exc)


@login_required
@require_feature("orchestrator")
@require_http_methods(["GET"])
def api_ide_read_file(request):
    """Return text content for a workspace file."""
    try:
        workspace_param = request.GET.get("workspace", "").strip()
        path_param = request.GET.get("path", "").strip()
        if not workspace_param or not path_param:
            return JsonResponse({"error": "workspace and path parameters are required"}, status=400)

        try:
            workspace_root = _resolve_ide_workspace(workspace_param)
            file_path = _resolve_workspace_child(workspace_root, path_param)
        except ValueError as exc:
            status = 403 if "outside" in str(exc).lower() else 400
            return JsonResponse({"error": str(exc)}, status=status)

        if not file_path.exists():
            return JsonResponse({"error": "File not found"}, status=404)
        if not file_path.is_file():
            return JsonResponse({"error": "Path is not a file"}, status=400)

        try:
            with open(file_path, encoding="utf-8") as file_obj:
                content = file_obj.read()
        except UnicodeDecodeError:
            return JsonResponse({"error": "File is not a text file"}, status=400)
        except PermissionError:
            return JsonResponse({"error": "Permission denied"}, status=403)
        except Exception as exc:
            logger.error(f"Error reading file {file_path}: {exc}")
            return internal_error_response(request, exc)

        return HttpResponse(content, content_type="text/plain; charset=utf-8")
    except Exception as exc:
        logger.error(f"api_ide_read_file error: {exc}")
        return internal_error_response(request, exc)


@login_required
@require_feature("orchestrator")
@require_http_methods(["PUT", "POST"])
def api_ide_write_file(request):
    """Create or update a text file inside a workspace."""
    try:
        if request.content_type and "application/json" in request.content_type:
            data = json.loads(request.body)
            workspace_param = data.get("workspace", "").strip()
            path_param = data.get("path", "").strip()
            content = data.get("content", "")
        else:
            workspace_param = request.GET.get("workspace", "").strip()
            path_param = request.GET.get("path", "").strip()
            content = request.body.decode("utf-8") if request.body else ""

        if not workspace_param or not path_param:
            return JsonResponse({"error": "workspace and path parameters are required"}, status=400)

        try:
            workspace_root = _resolve_ide_workspace(workspace_param)
            file_path = _resolve_workspace_child(workspace_root, path_param)
        except ValueError as exc:
            status = 403 if "outside" in str(exc).lower() else 400
            return JsonResponse({"error": str(exc)}, status=status)

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            return JsonResponse({"error": "Permission denied"}, status=403)
        except Exception as exc:
            logger.error(f"Error creating parent directories for {file_path}: {exc}")
            return internal_error_response(request, exc)

        try:
            with open(file_path, "w", encoding="utf-8") as file_obj:
                file_obj.write(content)
        except PermissionError:
            return JsonResponse({"error": "Permission denied"}, status=403)
        except Exception as exc:
            logger.error(f"Error writing file {file_path}: {exc}")
            return internal_error_response(request, exc)

        return JsonResponse(
            {
                "success": True,
                "path": str(file_path.relative_to(workspace_root)).replace("\\", "/"),
                "message": "File saved successfully",
            }
        )
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as exc:
        logger.error(f"api_ide_write_file error: {exc}")
        return internal_error_response(request, exc)


@login_required
@require_feature("orchestrator")
def ide_view(request):
    """Render the legacy web IDE page."""
    return render(request, "ide.html", {"project": request.GET.get("project", "").strip()})
