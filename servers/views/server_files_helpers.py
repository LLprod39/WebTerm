"""Shared helpers for SFTP file management views.

F-08a.10: extracted from ``server_files`` so the view module stays under the
legacy pin without behavior changes.
"""

from __future__ import annotations

import logging
import tempfile

from django.http import JsonResponse

from core_ui.api_failure import internal_error_response
from servers.elevated_files import ElevatedFileError

logger = logging.getLogger(__name__)


def _parse_bool(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _materialize_uploaded_file(uploaded_file) -> tuple[str, bool]:
    try:
        return uploaded_file.temporary_file_path(), False
    except (AttributeError, OSError):
        logger.debug("uploaded file has no usable temporary path", exc_info=True)

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        for chunk in uploaded_file.chunks():
            tmp.write(chunk)
        return tmp.name, True


def _sftp_error_response(exc: Exception) -> JsonResponse:
    import asyncssh as _asyncssh

    if isinstance(exc, ElevatedFileError):
        if exc.status >= 500:
            return internal_error_response(None, exc, status=exc.status)
        return JsonResponse(
            {"success": False, "error": str(exc) or "Elevated file operation failed", "code": exc.code},
            status=exc.status,
        )
    if isinstance(exc, (FileNotFoundError, _asyncssh.SFTPNoSuchFile, _asyncssh.SFTPNoSuchPath)):
        return JsonResponse({"success": False, "error": "Файл или папка не найдены", "code": "not_found"}, status=404)
    if isinstance(exc, (FileExistsError, _asyncssh.SFTPFileAlreadyExists)):
        return JsonResponse({"success": False, "error": "Файл уже существует", "code": "already_exists"}, status=409)
    if isinstance(exc, NotADirectoryError):
        return JsonResponse(
            {"success": False, "error": "Указанный путь не является папкой", "code": "not_a_directory"}, status=400
        )
    if isinstance(exc, IsADirectoryError):
        return JsonResponse(
            {"success": False, "error": "Операция требует файл, а не папку", "code": "is_directory"}, status=400
        )
    if isinstance(exc, (PermissionError, _asyncssh.SFTPPermissionDenied)):
        return JsonResponse(
            {
                "success": False,
                "error": "Недостаточно прав для выполнения операции",
                "code": "permission_denied",
            },
            status=403,
        )
    if isinstance(exc, ValueError):
        return JsonResponse({"success": False, "error": str(exc), "code": "invalid_request"}, status=400)
    return internal_error_response(None, exc)


def _missing_capability_response(capability: str) -> JsonResponse:
    return JsonResponse({"success": False, "error": f"Missing server capability: {capability}"}, status=403)


__all__ = [
    "_parse_bool",
    "_materialize_uploaded_file",
    "_sftp_error_response",
    "_missing_capability_response",
]
