"""Bounded, allowlisted GitLab repository archive loading for playbook imports."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import httpx
from django.conf import settings

from servers.services.playbooks.bundle_archive import BundleLimits, BundleValidationError


@dataclass(frozen=True)
class GitLabProjectArchive:
    content: bytes
    source: dict[str, str]


def fetch_gitlab_project_archive(
    *,
    project_url: str,
    ref: str = "",
    project_path: str = "",
    private_token: str = "",
    limits: BundleLimits | None = None,
    client: httpx.Client | None = None,
) -> GitLabProjectArchive:
    limits = limits or BundleLimits.from_settings()
    source = _normalize_source(project_url=project_url, ref=ref, project_path=project_path)
    api_url = urlunsplit(
        (
            "https",
            source["host"],
            f"/api/v4/projects/{quote(source['project'], safe='')}/repository/archive.tar.gz",
            "",
            "",
        )
    )
    params = {}
    if source.get("ref"):
        params["sha"] = source["ref"]
    if source.get("path"):
        params["path"] = source["path"]
    token = str(private_token or "").strip()
    if len(token) > 4096 or any(ord(char) < 32 for char in token):
        raise BundleValidationError("GitLab access token is invalid", code="invalid_gitlab_token")
    headers = {"Accept": "application/octet-stream", "User-Agent": "WebTerm-Playbook-Importer/1"}
    if token:
        headers["PRIVATE-TOKEN"] = token

    timeout = float(getattr(settings, "PLAYBOOK_GITLAB_TIMEOUT_SECONDS", 15) or 15)
    owned_client = client is None
    request_client = client or httpx.Client(timeout=timeout, follow_redirects=False)
    try:
        try:
            with request_client.stream(
                "GET",
                api_url,
                params=params,
                headers=headers,
                follow_redirects=False,
                timeout=timeout,
            ) as response:
                _raise_for_gitlab_status(response.status_code)
                declared_size = _content_length(response.headers.get("content-length"))
                if declared_size is not None and declared_size > limits.max_archive_bytes:
                    raise BundleValidationError(
                        "GitLab project archive exceeds the import size limit",
                        code="archive_size_limit",
                        status_code=413,
                    )
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > limits.max_archive_bytes:
                        raise BundleValidationError(
                            "GitLab project archive exceeds the import size limit",
                            code="archive_size_limit",
                            status_code=413,
                        )
        except BundleValidationError:
            raise
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise BundleValidationError(
                "GitLab could not be reached",
                code="gitlab_unavailable",
                status_code=502,
            ) from exc
    finally:
        if owned_client:
            request_client.close()

    if not content:
        raise BundleValidationError("GitLab returned an empty archive", code="empty_archive")
    return GitLabProjectArchive(content=bytes(content), source=source)


def _normalize_source(*, project_url: str, ref: str, project_path: str) -> dict[str, str]:
    raw_url = str(project_url or "").strip()
    if not raw_url or len(raw_url) > 2048:
        raise BundleValidationError("Enter a valid GitLab project URL", code="invalid_gitlab_url")
    parsed = urlsplit(raw_url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise BundleValidationError("GitLab project URL must use HTTPS", code="invalid_gitlab_url")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise BundleValidationError(
            "GitLab project URL must not contain credentials, query parameters, or fragments",
            code="invalid_gitlab_url",
        )
    try:
        port = parsed.port
    except ValueError as exc:
        raise BundleValidationError("GitLab project URL has an invalid port", code="invalid_gitlab_url") from exc
    if port not in {None, 443}:
        raise BundleValidationError("GitLab project URL must use the standard HTTPS port", code="invalid_gitlab_url")

    host = parsed.hostname.casefold().rstrip(".")
    if host not in _allowed_hosts():
        raise BundleValidationError(
            "This GitLab host is not allowed by the WebTerm administrator",
            code="gitlab_host_not_allowed",
            status_code=403,
        )
    project = unquote(parsed.path).strip("/")
    if project.endswith(".git"):
        project = project[:-4]
    project_parts = project.split("/")
    if len(project_parts) < 2 or any(part in {"", ".", ".."} for part in project_parts):
        raise BundleValidationError("GitLab URL must point to a group/project", code="invalid_gitlab_url")
    if len(project) > 500 or any(len(part) > 150 for part in project_parts):
        raise BundleValidationError("GitLab project path is too long", code="invalid_gitlab_url")

    normalized_ref = str(ref or "").strip()
    if len(normalized_ref) > 200 or any(ord(char) < 32 for char in normalized_ref):
        raise BundleValidationError("Git reference is invalid", code="invalid_gitlab_ref")
    normalized_path = str(project_path or "").strip().strip("/").replace("\\", "/")
    path_parts = normalized_path.split("/") if normalized_path else []
    if len(normalized_path) > 300 or any(part in {"", ".", ".."} for part in path_parts):
        raise BundleValidationError("Repository directory is invalid", code="invalid_gitlab_path")

    return {
        "type": "gitlab",
        "host": host,
        "project": project,
        **({"ref": normalized_ref} if normalized_ref else {}),
        **({"path": normalized_path} if normalized_path else {}),
    }


def _allowed_hosts() -> set[str]:
    configured = getattr(settings, "PLAYBOOK_GITLAB_ALLOWED_HOSTS", ("gitlab.com",))
    values = configured.split(",") if isinstance(configured, str) else configured
    return {str(value).strip().casefold().rstrip(".") for value in values if str(value).strip()}


def _raise_for_gitlab_status(status_code: int) -> None:
    if status_code == 200:
        return
    if status_code in {301, 302, 303, 307, 308}:
        raise BundleValidationError(
            "GitLab redirected the archive request", code="gitlab_redirect_rejected", status_code=502
        )
    if status_code in {401, 403}:
        raise BundleValidationError("GitLab rejected the access token", code="gitlab_auth_failed", status_code=422)
    if status_code == 404:
        raise BundleValidationError(
            "GitLab project, ref, or directory was not found", code="gitlab_project_not_found", status_code=404
        )
    raise BundleValidationError("GitLab archive request failed", code="gitlab_unavailable", status_code=502)


def _content_length(value: str | None) -> int | None:
    if not value:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None
