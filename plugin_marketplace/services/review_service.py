from __future__ import annotations

from django.db import transaction

from core_ui.models import UserActivityLog
from plugin_marketplace.models import PluginPackage
from plugin_marketplace.services.serialization import package_payload


def list_review_packages() -> list[dict]:
    packages = PluginPackage.objects.order_by("review_status", "-updated_at", "plugin_id")
    return [package_payload(package, include_manifest=True) for package in packages]


@transaction.atomic
def mark_package_review(
    package_id: int,
    status: str,
    *,
    notes: str = "",
    rejection_reason: str = "",
    sign_when_verified: bool = True,
    actor=None,
    request=None,
) -> PluginPackage:
    valid = {choice[0] for choice in PluginPackage.REVIEW_CHOICES}
    if status not in valid:
        raise ValueError(f"Unknown review status: {status}")
    package = PluginPackage.objects.select_for_update().get(id=package_id)
    package.review_status = status
    package.save(update_fields=["review_status", "updated_at"])
    if status == PluginPackage.REVIEW_VERIFIED and sign_when_verified and package.signature_status != PluginPackage.SIGNATURE_BUILTIN:
        from plugin_marketplace.services.signing_service import sign_package

        package = sign_package(package.id, actor=actor, request=request)
    from plugin_marketplace.services.install_service import record_event

    record_event(
        plugin_id=package.plugin_id,
        event_type="plugin_package_reviewed",
        status=UserActivityLog.STATUS_SUCCESS,
        actor=actor,
        request=request,
        message=f"Plugin package review status changed to {status}.",
        metadata={
            "package_id": package.id,
            "review_status": status,
            "notes": notes,
            "rejection_reason": rejection_reason,
        },
    )
    return package
