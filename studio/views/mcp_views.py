"""
Studio MCP pool endpoints.
"""

import asyncio
import subprocess
import sys

import httpx
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from core_ui.managed_secrets import get_mcp_secret_env, get_mcp_secret_env_keys
from studio.mcp_client import MCPClientError, inspect_mcp_server
from studio.mcp_runner_client import _mcp_runner_url
from studio.mcp_security import (
    build_mcp_subprocess_env,
    validate_mcp_runtime_policy,
    validate_sse_mcp_policy,
    validate_stdio_mcp_policy,
)
from studio.models import MCPServerPool

STUDIO_FEATURE_MCP = "studio_mcp"

MCP_TEMPLATES = [
    {
        "slug": "github",
        "name": "GitHub",
        "description": "GitHub repository management via MCP",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": ""},
        "icon": "🐙",
    },
    {
        "slug": "filesystem",
        "name": "Filesystem",
        "description": "Read/write local filesystem via MCP",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed"],
        "env": {},
        "icon": "📁",
    },
    {
        "slug": "kubernetes",
        "name": "Kubernetes",
        "description": "Manage Kubernetes clusters via kubectl MCP",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-kubernetes"],
        "env": {"KUBECONFIG": "~/.kube/config"},
        "icon": "☸️",
    },
    {
        "slug": "docker",
        "name": "Docker",
        "description": "Manage Docker containers and images",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-docker"],
        "env": {},
        "icon": "🐳",
    },
    {
        "slug": "postgres",
        "name": "PostgreSQL",
        "description": "Query and manage PostgreSQL databases",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres"],
        "env": {"POSTGRES_CONNECTION_STRING": "postgresql://user:pass@localhost/db"},
        "icon": "🐘",
    },
    {
        "slug": "slack",
        "name": "Slack",
        "description": "Send notifications and interact with Slack",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-slack"],
        "env": {"SLACK_BOT_TOKEN": "", "SLACK_TEAM_ID": ""},
        "icon": "💬",
    },
    {
        "slug": "custom_python",
        "name": "Custom Python MCP",
        "description": "Your own Python MCP server",
        "transport": "stdio",
        "command": "python",
        "args": ["path/to/your_mcp_server.py"],
        "env": {},
        "icon": "🐍",
    },
]


def _json_body(request) -> dict:
    import json

    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _err(msg: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": msg}, status=status)


def _ok(data, status: int = 200) -> JsonResponse:
    return JsonResponse(data, safe=False, status=status)


def _is_admin(user) -> bool:
    return bool(user and getattr(user, "is_authenticated", False) and getattr(user, "is_staff", False))


def _owner_payload(owner: User | None) -> dict | None:
    if owner is None:
        return None
    return {"id": owner.id, "username": owner.username}


def _shared_user_payloads(shared_users) -> list[dict]:
    return [{"id": user.id, "username": user.username} for user in shared_users]


def _access_mode(*, owner_id: int | None, viewer) -> str:
    if _is_admin(viewer) and owner_id and owner_id != viewer.id:
        return "admin"
    if owner_id == getattr(viewer, "id", None):
        return "owner"
    return "shared"


def _normalise_related_ids(raw_values) -> list[int]:
    if not isinstance(raw_values, list):
        return []
    ids: list[int] = []
    for item in raw_values:
        try:
            ids.append(int(item))
        except (TypeError, ValueError):
            continue
    return ids


def _apply_shared_users(instance, shared_user_ids: list[int]):
    if instance.owner_id:
        shared_user_ids = [user_id for user_id in shared_user_ids if user_id != instance.owner_id]
    users = User.objects.filter(id__in=shared_user_ids, is_active=True).order_by("username")
    instance.shared_with.set(users)


def _mcp_read_queryset_for_user(user):
    qs = MCPServerPool.objects.select_related("owner").prefetch_related("shared_with")
    if _is_admin(user):
        return qs.order_by("name")
    return qs.filter(Q(owner=user) | Q(is_shared=True) | Q(shared_with=user)).distinct().order_by("name")


def _mcp_write_queryset_for_user(user):
    qs = MCPServerPool.objects.select_related("owner").prefetch_related("shared_with")
    if _is_admin(user):
        return qs
    return qs.filter(owner=user)


def _mcp_to_dict(mcp: MCPServerPool, viewer) -> dict:
    can_edit = _is_admin(viewer) or mcp.owner_id == getattr(viewer, "id", None)
    shared_users = _shared_user_payloads(mcp.shared_with.all())
    return {
        "id": mcp.pk,
        "name": mcp.name,
        "description": mcp.description,
        "transport": mcp.transport,
        "command": mcp.command,
        "args": mcp.args,
        "env": mcp.env if can_edit else {},
        "secret_env_keys": get_mcp_secret_env_keys(mcp.id) if can_edit else [],
        "url": mcp.url,
        "headers": mcp.headers if can_edit else {},
        "is_shared": bool(mcp.is_shared or shared_users),
        "shared_user_ids": [item["id"] for item in shared_users],
        "shared_users": shared_users,
        "owner": _owner_payload(mcp.owner),
        "owner_username": mcp.owner.username,
        "is_owner": mcp.owner_id == getattr(viewer, "id", None),
        "can_edit": can_edit,
        "can_share": _is_admin(viewer),
        "access_mode": _access_mode(owner_id=mcp.owner_id, viewer=viewer),
        "last_test_ok": mcp.last_test_ok,
        "last_test_at": mcp.last_test_at.isoformat() if mcp.last_test_at else None,
        "last_test_error": mcp.last_test_error,
    }


def _normalize_sse_url(url: str) -> str:
    """Ensure SSE URL has http:// or https:// so httpx/requests accept it."""
    normalized_url = (url or "").strip()
    if not normalized_url:
        return normalized_url
    if normalized_url.startswith(("http://", "https://")):
        return normalized_url
    return "http://" + normalized_url


def _validate_mcp_payload_policy(data: dict, user, *, existing: MCPServerPool | None = None, action: str = "create"):
    transport = data.get("transport", existing.transport if existing else MCPServerPool.TRANSPORT_STDIO)
    if transport == MCPServerPool.TRANSPORT_STDIO:
        command = data.get("command", existing.command if existing else "")
        raw_args = data.get("args", existing.args if existing else [])
        args = raw_args if isinstance(raw_args, list) else None
        policy = validate_stdio_mcp_policy(str(command or ""), args, user=user, action=action)
    else:
        url = data.get("url", existing.url if existing else "")
        policy = validate_sse_mcp_policy(str(url or ""), user=user, action=action)
    if not policy.allowed:
        return _err(policy.error, 403)
    return None


def _default_test_mcp_connection(mcp: MCPServerPool) -> tuple[bool, str | None]:
    """Basic connectivity test for MCP server."""
    if mcp.transport == MCPServerPool.TRANSPORT_SSE:
        url = _normalize_sse_url(mcp.url or "")
        if not url:
            return False, "SSE URL is required"
        headers = {str(k): str(v) for k, v in (mcp.headers or {}).items() if str(k).strip()}
        secret_env = get_mcp_secret_env(mcp.id) if mcp.id else {}
        token = str(secret_env.get("MCP_BEARER_TOKEN") or "").strip()
        if token and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {token}"
        raw_auth = str(secret_env.get("MCP_AUTHORIZATION") or "").strip()
        if raw_auth:
            headers["Authorization"] = raw_auth
        try:
            response = httpx.get(url, timeout=10, headers=headers or None)
            response.raise_for_status()
            content_type = (response.headers.get("content-type") or "").lower()
            if "text/html" in content_type:
                return False, "MCP endpoint returned HTML instead of JSON/SSE"
            return True, None
        except Exception as exc:
            return False, str(exc)

    if not mcp.command:
        return False, "No command configured"
    policy = validate_mcp_runtime_policy(mcp, action="test")
    if not policy.allowed:
        return False, policy.error
    # With the Runner active, stdio MCP never runs on the backend host — probe it
    # end-to-end through the Runner (spawn + initialize + tools/list) instead.
    if _mcp_runner_url():
        try:
            asyncio.run(_inspect_mcp_server(mcp))
            return True, None
        except MCPClientError as exc:
            return False, str(exc)
        except Exception as exc:
            return False, str(exc)
    try:
        env = build_mcp_subprocess_env(mcp.env, get_mcp_secret_env(mcp.id))
        proc = subprocess.Popen(
            [mcp.command] + (mcp.args or []),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        try:
            proc.communicate(timeout=5)
            return True, None
        except subprocess.TimeoutExpired:
            proc.kill()
            return True, None
    except FileNotFoundError:
        return False, f"Command not found: {mcp.command}"
    except Exception as exc:
        return False, str(exc)


def _test_mcp_connection(mcp: MCPServerPool) -> tuple[bool, str | None]:
    package = sys.modules.get("studio.views")
    tester = getattr(package, "_test_mcp_connection", _default_test_mcp_connection)
    if tester is _test_mcp_connection:
        tester = _default_test_mcp_connection
    return tester(mcp)


def _inspect_mcp_server(mcp: MCPServerPool):
    package = sys.modules.get("studio.views")
    inspector = getattr(package, "inspect_mcp_server", inspect_mcp_server)
    return inspector(mcp)


@require_feature(STUDIO_FEATURE_MCP)
def api_mcp_list(request):
    if request.method == "GET":
        qs = _mcp_read_queryset_for_user(request.user)
        return _ok([_mcp_to_dict(mcp, request.user) for mcp in qs])

    if request.method == "POST":
        data = _json_body(request)
        name = data.get("name", "").strip()
        if not name:
            return _err("name is required")
        transport = data.get("transport", MCPServerPool.TRANSPORT_STDIO)
        url = (data.get("url") or "").strip()
        if transport == MCPServerPool.TRANSPORT_SSE and url:
            url = _normalize_sse_url(url)
        policy_error = _validate_mcp_payload_policy(data, request.user, action="create")
        if policy_error is not None:
            return policy_error
        mcp = MCPServerPool.objects.create(
            name=name,
            description=data.get("description", ""),
            transport=transport,
            command=data.get("command", ""),
            args=data.get("args", []),
            env=data.get("env", {}),
            url=url,
            headers=data.get("headers") if isinstance(data.get("headers"), dict) else {},
            owner=request.user,
        )
        if _is_admin(request.user):
            if "is_shared" in data:
                mcp.is_shared = bool(data.get("is_shared"))
                mcp.save(update_fields=["is_shared"])
            if "shared_user_ids" in data:
                _apply_shared_users(mcp, _normalise_related_ids(data.get("shared_user_ids")))
        return _ok(_mcp_to_dict(mcp, request.user), status=201)

    return _err("Method not allowed", 405)


@require_feature(STUDIO_FEATURE_MCP)
def api_mcp_detail(request, mcp_id: int):
    mcp = _mcp_read_queryset_for_user(request.user).filter(pk=mcp_id).first()
    if mcp is None:
        return _err("MCP server not found", 404)
    can_edit = _is_admin(request.user) or mcp.owner_id == request.user.id

    if request.method == "GET":
        return _ok(_mcp_to_dict(mcp, request.user))

    if request.method == "PUT":
        if not can_edit:
            return _err("Only the owner or admin can edit this MCP server", 403)
        data = _json_body(request)
        policy_error = _validate_mcp_payload_policy(data, request.user, existing=mcp, action="edit")
        if policy_error is not None:
            return policy_error
        for field in ("name", "description", "transport", "command", "args", "env", "url", "headers"):
            if field in data:
                val = data[field]
                if field == "url" and (mcp.transport or data.get("transport")) == MCPServerPool.TRANSPORT_SSE and val:
                    val = _normalize_sse_url((val or "").strip())
                if field == "headers" and not isinstance(val, dict):
                    val = {}
                setattr(mcp, field, val)
        mcp.save()
        if _is_admin(request.user):
            if "is_shared" in data:
                mcp.is_shared = bool(data.get("is_shared"))
                mcp.save(update_fields=["is_shared"])
            if "shared_user_ids" in data:
                _apply_shared_users(mcp, _normalise_related_ids(data.get("shared_user_ids")))
        return _ok(_mcp_to_dict(mcp, request.user))

    if request.method == "DELETE":
        if not can_edit:
            return _err("Only the owner or admin can delete this MCP server", 403)
        mcp.delete()
        return JsonResponse({"ok": True})

    return _err("Method not allowed", 405)


@require_feature(STUDIO_FEATURE_MCP)
@require_http_methods(["POST"])
def api_mcp_test(request, mcp_id: int):
    mcp = _mcp_write_queryset_for_user(request.user).filter(pk=mcp_id).first()
    if mcp is None:
        return _err("MCP server not found", 404)
    policy = validate_mcp_runtime_policy(mcp, user=request.user, action="test")
    if not policy.allowed:
        return _err(policy.error, 403)

    ok, error = _test_mcp_connection(mcp)
    mcp.last_test_ok = ok
    mcp.last_test_at = timezone.now()
    mcp.last_test_error = error or ""
    mcp.save(update_fields=["last_test_ok", "last_test_at", "last_test_error"])
    return _ok({"ok": ok, "error": error})


@require_feature(STUDIO_FEATURE_MCP)
def api_mcp_templates(request):
    return _ok(MCP_TEMPLATES)


@require_feature(STUDIO_FEATURE_MCP)
@require_http_methods(["GET"])
def api_mcp_tools(request, mcp_id: int):
    mcp = _mcp_read_queryset_for_user(request.user).filter(pk=mcp_id).first()
    if mcp is None:
        return _err("MCP server not found", 404)
    policy = validate_mcp_runtime_policy(mcp, user=request.user, action="inspect")
    if not policy.allowed:
        return _err(policy.error, 403)

    try:
        return _ok(asyncio.run(_inspect_mcp_server(mcp)))
    except MCPClientError as exc:
        return _err(str(exc), 400)
    except Exception as exc:
        return _err(f"Failed to inspect MCP server: {exc}", 500)
