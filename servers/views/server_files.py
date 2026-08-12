"""
SFTP file management endpoints.

These views keep the HTTP/API layer for remote file operations separate from
the larger legacy server view module. The SSH auth/access helpers are still
shared with Linux UI endpoints until that slice is extracted too.

F-08a.10: error/upload helpers live in ``server_files_helpers``.
"""

import contextlib
import json
import os

from asgiref.sync import async_to_sync
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from core_ui.activity import log_user_activity
from core_ui.decorators import require_feature
from core_ui.models import UserActivityLog
from servers.elevated_files import read_text_file_elevated, write_text_file_elevated
from servers.services.server_mutation_policy import decide_server_mutation
from servers.sftp import (
    change_owner,
    change_permissions,
    create_directory,
    delete_path,
    download_file,
    get_directory_listing,
    read_text_file,
    rename_path,
    upload_local_file,
    write_text_file,
)
from servers.views.server_files_helpers import (
    _materialize_uploaded_file,
    _missing_capability_response,
    _parse_bool,
    _sftp_error_response,
)
from servers.views.server_helpers import (
    _accessible_servers_queryset,
    _require_ssh_server,
    _resolve_server_secret,
    _server_has_capability,
)

__all__ = [
    "_parse_bool",
    "_materialize_uploaded_file",
    "_sftp_error_response",
    "_missing_capability_response",
    "server_file_list",
    "server_file_read_text",
    "server_file_write_text",
    "server_file_chmod",
    "server_file_chown",
    "server_file_upload",
    "server_file_download",
    "server_file_rename",
    "server_file_delete",
    "server_file_mkdir",
]


def _mutation_policy_response(request, server):
    decision = decide_server_mutation(request.user, server, request=request)
    if decision.allowed:
        return None
    return JsonResponse(
        {"success": False, "error": decision.message, "code": decision.code},
        status=403,
    )


@login_required
@require_feature("servers")
@require_http_methods(["GET"])
def server_file_list(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "read_files"):
        return _missing_capability_response("read_files")
    try:
        _require_ssh_server(server)
        password = _resolve_server_secret(server, request, request.GET)
        result = async_to_sync(get_directory_listing)(
            server,
            secret=password or "",
            path=request.GET.get("path") or ".",
            user_id=request.user.id,
        )
        return JsonResponse({"success": True, **result})
    except Exception as exc:
        return _sftp_error_response(exc)


@login_required
@require_feature("servers")
@require_http_methods(["GET", "POST"])
def server_file_read_text(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "read_files"):
        return _missing_capability_response("read_files")
    try:
        _require_ssh_server(server)
        # Prefer JSON body for elevate + sudo_password (never put secrets in query string).
        body = {}
        if request.method == "POST":
            with contextlib.suppress(Exception):
                body = json.loads(request.body or "{}") or {}
        params = request.GET if request.method == "GET" else body
        elevate = _parse_bool(params.get("elevate") if isinstance(params, dict) else request.GET.get("elevate"))
        if elevate and (denied := _mutation_policy_response(request, server)):
            return denied
        password = _resolve_server_secret(server, request, params if isinstance(params, dict) else request.GET)
        # Password only accepted from POST body.
        sudo_password = str(body.get("sudo_password") or "") if request.method == "POST" else ""
        path = str((params.get("path") if isinstance(params, dict) else None) or request.GET.get("path") or "")
        if elevate:
            result = async_to_sync(read_text_file_elevated)(
                server,
                secret=password or "",
                path=path,
                sudo_password=sudo_password,
                user_id=request.user.id,
            )
        else:
            result = async_to_sync(read_text_file)(
                server,
                secret=password or "",
                path=path,
                user_id=request.user.id,
            )
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_file_read_text",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Read text file on "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
            metadata={
                "path": result["path"],
                "size": result["size"],
                "elevated": bool(elevate),
            },
        )
        return JsonResponse({"success": True, "file": result})
    except Exception as exc:
        return _sftp_error_response(exc)


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_file_write_text(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "write_files"):
        return _missing_capability_response("write_files")
    if denied := _mutation_policy_response(request, server):
        return denied
    try:
        _require_ssh_server(server)
        data = json.loads(request.body or "{}")
        password = _resolve_server_secret(server, request, data)
        elevate = _parse_bool(data.get("elevate"))
        sudo_password = str(data.get("sudo_password") or "")
        path = str(data.get("path") or "")
        content = str(data.get("content") or "")
        if elevate:
            result = async_to_sync(write_text_file_elevated)(
                server,
                secret=password or "",
                path=path,
                content=content,
                sudo_password=sudo_password,
                user_id=request.user.id,
            )
        else:
            result = async_to_sync(write_text_file)(
                server,
                secret=password or "",
                path=path,
                content=content,
                user_id=request.user.id,
            )
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_file_write_text",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Updated text file on "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
            metadata={
                "path": result["path"],
                "size": result["size"],
                "elevated": bool(elevate),
            },
        )
        return JsonResponse({"success": True, "file": result})
    except Exception as exc:
        return _sftp_error_response(exc)


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_file_chmod(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "write_files"):
        return _missing_capability_response("write_files")
    if denied := _mutation_policy_response(request, server):
        return denied
    try:
        _require_ssh_server(server)
        data = json.loads(request.body or "{}")
        password = _resolve_server_secret(server, request, data)
        result = async_to_sync(change_permissions)(
            server,
            secret=password or "",
            path=str(data.get("path") or ""),
            mode=str(data.get("mode") or ""),
            user_id=request.user.id,
        )
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_file_chmod",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Changed file permissions on "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
            metadata={"path": result["entry"]["path"], "mode": data.get("mode")},
        )
        return JsonResponse({"success": True, **result})
    except Exception as exc:
        return _sftp_error_response(exc)


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_file_chown(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "write_files"):
        return _missing_capability_response("write_files")
    if denied := _mutation_policy_response(request, server):
        return denied
    try:
        _require_ssh_server(server)
        data = json.loads(request.body or "{}")
        password = _resolve_server_secret(server, request, data)
        owner_spec = str(data.get("owner") or "").strip()
        owner_name = owner_spec
        group_name = ""
        if ":" in owner_spec:
            owner_name, group_name = owner_spec.split(":", 1)

        result = async_to_sync(change_owner)(
            server,
            secret=password or "",
            path=str(data.get("path") or ""),
            owner=owner_name or None,
            group=group_name or None,
            recursive=bool(data.get("recursive")),
            user_id=request.user.id,
        )
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_file_chown",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Changed file owner on "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
            metadata={
                "path": result["entry"]["path"],
                "owner": owner_spec,
                "recursive": bool(data.get("recursive")),
            },
        )
        return JsonResponse({"success": True, **result})
    except Exception as exc:
        return _sftp_error_response(exc)


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_file_upload(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "write_files"):
        return _missing_capability_response("write_files")
    if denied := _mutation_policy_response(request, server):
        return denied
    try:
        _require_ssh_server(server)
        password = _resolve_server_secret(server, request, request.POST)
        target_path = request.POST.get("path") or "."
        overwrite = _parse_bool(request.POST.get("overwrite"))
        uploaded_files = request.FILES.getlist("files")
        if not uploaded_files:
            return JsonResponse({"success": False, "error": "Нет файлов для загрузки"}, status=400)

        uploaded_entries = []
        current_path = target_path
        for uploaded_file in uploaded_files:
            local_path, should_cleanup = _materialize_uploaded_file(uploaded_file)
            try:
                result = async_to_sync(upload_local_file)(
                    server,
                    secret=password or "",
                    remote_dir=target_path,
                    local_path=local_path,
                    remote_name=uploaded_file.name,
                    overwrite=overwrite,
                    user_id=request.user.id,
                )
                current_path = result["path"]
                uploaded_entries.append(result["entry"])
            finally:
                if should_cleanup:
                    with contextlib.suppress(OSError):
                        os.remove(local_path)

        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_file_upload",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Uploaded {len(uploaded_entries)} file(s) to "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
            metadata={"path": current_path, "count": len(uploaded_entries)},
        )
        return JsonResponse({"success": True, "path": current_path, "entries": uploaded_entries})
    except Exception as exc:
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_file_upload",
            status=UserActivityLog.STATUS_ERROR,
            description=f'File upload failed for "{server.name}" (internal_error)',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
        )
        return _sftp_error_response(exc)


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_file_download(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "read_files"):
        return _missing_capability_response("read_files")
    try:
        _require_ssh_server(server)
        data = json.loads(request.body or "{}")
        password = _resolve_server_secret(server, request, data)
        target_path = str(data.get("path") or "").strip()
        if not target_path:
            return JsonResponse({"success": False, "error": "Не указан путь к файлу"}, status=400)

        result = async_to_sync(download_file)(server, secret=password or "", path=target_path, user_id=request.user.id)
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_file_download",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Downloaded file from "{server.name}": {result["filename"]}',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
            metadata={"path": result["path"], "size": result["size"]},
        )
        response = FileResponse(result["file_obj"], as_attachment=True, filename=result["filename"])
        response["Content-Length"] = str(result["size"])
        response["X-Remote-Path"] = result["path"]
        return response
    except Exception as exc:
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_file_download",
            status=UserActivityLog.STATUS_ERROR,
            description=f'File download failed for "{server.name}" (internal_error)',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
        )
        return _sftp_error_response(exc)


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_file_rename(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "write_files"):
        return _missing_capability_response("write_files")
    if denied := _mutation_policy_response(request, server):
        return denied
    try:
        _require_ssh_server(server)
        data = json.loads(request.body or "{}")
        password = _resolve_server_secret(server, request, data)
        source_path = str(data.get("path") or "").strip()
        new_name = str(data.get("new_name") or "").strip()
        if not source_path or not new_name:
            return JsonResponse({"success": False, "error": "Нужны path и new_name"}, status=400)

        result = async_to_sync(rename_path)(
            server,
            secret=password or "",
            path=source_path,
            new_name=new_name,
            user_id=request.user.id,
        )
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_file_rename",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Renamed remote entry on "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
            metadata={"path": source_path, "new_name": new_name},
        )
        return JsonResponse({"success": True, **result})
    except Exception as exc:
        return _sftp_error_response(exc)


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_file_delete(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "write_files"):
        return _missing_capability_response("write_files")
    if denied := _mutation_policy_response(request, server):
        return denied
    try:
        _require_ssh_server(server)
        data = json.loads(request.body or "{}")
        password = _resolve_server_secret(server, request, data)
        target_path = str(data.get("path") or "").strip()
        recursive = _parse_bool(data.get("recursive"))
        if not target_path:
            return JsonResponse({"success": False, "error": "Не указан path"}, status=400)

        result = async_to_sync(delete_path)(
            server,
            secret=password or "",
            path=target_path,
            recursive=recursive,
            user_id=request.user.id,
        )
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_file_delete",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Deleted remote entry on "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
            metadata={"path": result["deleted_path"], "recursive": recursive},
        )
        return JsonResponse({"success": True, **result})
    except Exception as exc:
        return _sftp_error_response(exc)


@login_required
@require_feature("servers")
@require_http_methods(["POST"])
def server_file_mkdir(request, server_id):
    server = get_object_or_404(_accessible_servers_queryset(request.user), id=server_id)
    if not _server_has_capability(server, request.user, "write_files"):
        return _missing_capability_response("write_files")
    if denied := _mutation_policy_response(request, server):
        return denied
    try:
        _require_ssh_server(server)
        data = json.loads(request.body or "{}")
        password = _resolve_server_secret(server, request, data)
        parent_path = str(data.get("path") or ".").strip() or "."
        folder_name = str(data.get("name") or "").strip()
        if not folder_name:
            return JsonResponse({"success": False, "error": "Не указано имя папки"}, status=400)

        result = async_to_sync(create_directory)(
            server,
            secret=password or "",
            parent_path=parent_path,
            name=folder_name,
            user_id=request.user.id,
        )
        log_user_activity(
            user=request.user,
            request=request,
            category="servers",
            action="server_file_mkdir",
            status=UserActivityLog.STATUS_SUCCESS,
            description=f'Created remote directory on "{server.name}"',
            entity_type="server",
            entity_id=server.id,
            entity_name=server.name,
            metadata={"path": result["path"], "name": folder_name},
        )
        return JsonResponse({"success": True, **result})
    except Exception as exc:
        return _sftp_error_response(exc)
