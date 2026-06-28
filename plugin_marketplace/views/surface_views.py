from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from app.plugins.agent_tools import active_agent_tools
from app.plugins.connectors import active_connectors
from app.plugins.dashboard import active_dashboard_widgets
from app.plugins.hooks import active_hooks
from app.plugins.pages import active_plugin_pages
from app.plugins.studio_nodes import active_studio_nodes
from app.plugins.terminal_actions import active_terminal_actions
from core_ui.decorators import require_feature
from plugin_marketplace.models import PluginInstallation
from plugin_marketplace.services.frontend_bundle_policy_service import (
    DYNAMIC_FRONTEND_BUNDLE_RENDERERS,
    frontend_bundle_policy_for_package,
)
from plugin_marketplace.services.install_service import enabled_plugin_ids_for_user
from plugin_marketplace.views.common import json_error


def _enabled_installations_by_plugin(enabled_ids: set[str]) -> dict[str, PluginInstallation]:
    return {
        installation.plugin_id: installation
        for installation in PluginInstallation.objects.select_related("package").filter(
            plugin_id__in=enabled_ids,
            status=PluginInstallation.STATUS_ENABLED,
        )
    }


def _surface_with_runtime_policy(surface: dict, installation: PluginInstallation | None) -> dict | None:
    renderer = str(surface.get("renderer") or "").strip().lower()
    if renderer not in DYNAMIC_FRONTEND_BUNDLE_RENDERERS:
        return surface
    if installation is None:
        return None
    policy = frontend_bundle_policy_for_package(installation.package)
    if not policy.get("allowed"):
        return None
    bundle_url = str(surface.get("bundle_url") or surface.get("src") or "").strip()
    bundle_sha256 = str(surface.get("bundle_sha256") or surface.get("sha256") or "").strip().lower()
    return {
        **surface,
        "frontend_bundle_runtime": {
            "renderer": renderer,
            "bundle_url": bundle_url,
            "bundle_sha256": bundle_sha256,
            "sandbox": {"allow_scripts": True},
            "required_attestation_kind": policy.get("required_attestation_kind"),
        },
    }


def _active_pages(enabled_ids: set[str]) -> list[dict]:
    installations = _enabled_installations_by_plugin(enabled_ids)
    pages: list[dict] = []
    for page in active_plugin_pages(enabled_ids):
        runtime_page = _surface_with_runtime_policy(page, installations.get(str(page.get("plugin_id") or "")))
        if runtime_page is not None:
            pages.append(runtime_page)
    return pages


def _active_dashboard_widgets(enabled_ids: set[str]) -> list[dict]:
    installations = _enabled_installations_by_plugin(enabled_ids)
    widgets: list[dict] = []
    for widget in active_dashboard_widgets(enabled_ids):
        runtime_widget = _surface_with_runtime_policy(widget, installations.get(str(widget.get("plugin_id") or "")))
        if runtime_widget is not None:
            widgets.append(runtime_widget)
    return widgets


def _surface_payload(enabled_ids: set[str]) -> dict:
    return {
        "pages": _active_pages(enabled_ids),
        "dashboard_widgets": _active_dashboard_widgets(enabled_ids),
        "connectors": active_connectors(enabled_ids),
        "studio_nodes": active_studio_nodes(enabled_ids),
        "agent_tools": active_agent_tools(enabled_ids),
        "terminal_actions": active_terminal_actions(enabled_ids),
        "hooks": active_hooks(enabled_ids),
    }


@login_required
@require_feature("settings")
@require_GET
def active_surfaces(request):
    surfaces = _surface_payload(enabled_plugin_ids_for_user(request.user))
    return JsonResponse({"success": True, "surfaces": surfaces})


@login_required
@require_feature("settings")
@require_GET
def plugin_page(request, plugin_id: str, page_id: str):
    for page in _active_pages(enabled_plugin_ids_for_user(request.user)):
        if page.get("plugin_id") == plugin_id and page.get("id") == page_id:
            return JsonResponse({"success": True, "page": page})
    return json_error("Plugin page was not found or the plugin is disabled.", status=404, code="not_found")
