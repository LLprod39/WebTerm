from __future__ import annotations

from django.conf import settings
from django.core.checks import Error, Tags, register

from plugin_marketplace.release_profile import (
    PLUGIN_MARKETPLACE_MODE_DISABLED,
    PLUGIN_MARKETPLACE_RELEASE_MODES,
    plugin_marketplace_release_mode,
)
from plugin_marketplace.services.backend_container_runner_service import is_immutable_plugin_backend_image
from plugin_marketplace.services.backend_sandbox_runner_service import (
    BACKEND_SANDBOX_PROVIDER_DISABLED,
    BACKEND_SANDBOX_PROVIDER_DOCKER,
    BACKEND_SANDBOX_PROVIDER_EXTERNAL,
    BACKEND_SANDBOX_PROVIDERS,
)
from plugin_marketplace.services.compatibility_matrix_service import COMPATIBILITY_JOB_ISOLATION_MODES
from plugin_marketplace.services.dependency_policy_service import invalid_dependency_allowlist_entries
from plugin_marketplace.services.frontend_bundle_policy_service import FRONTEND_BUNDLE_REVIEW_ATTESTATION_KIND
from plugin_marketplace.services.package_attestation_policy_service import invalid_required_attestation_kinds


def _docker_backend_runner_errors(*, provider: str, runner_image: str, docker_host: str) -> list[Error]:
    if provider != BACKEND_SANDBOX_PROVIDER_DOCKER:
        return []
    errors: list[Error] = []
    if not is_immutable_plugin_backend_image(runner_image):
        errors.append(
            Error(
                "Plugin Marketplace Docker runner image is not immutable.",
                hint="Set PLUGIN_BACKEND_RUNNER_IMAGE to a repository@sha256 digest or sha256 image ID.",
                id="plugin_marketplace.E032",
            )
        )
    if not docker_host.startswith("tcp://"):
        errors.append(
            Error(
                "Plugin Marketplace Docker runner is not routed through a filtered TCP proxy.",
                hint="Set PLUGIN_BACKEND_DOCKER_HOST to the dedicated plugin backend Docker proxy.",
                id="plugin_marketplace.E033",
            )
        )
    return errors


def _backend_sandbox_provider_errors(
    *,
    provider: str,
    external_endpoint: str,
    runner_image: str,
    docker_host: str,
    allow_sandboxed_code: bool,
    backend_sandbox: bool,
    frontend_sandbox: bool,
) -> list[Error]:
    errors: list[Error] = []
    if provider not in BACKEND_SANDBOX_PROVIDERS:
        errors.append(
            Error(
                "Plugin Marketplace backend sandbox provider is unknown.",
                hint=f"Set PLUGIN_MARKETPLACE_BACKEND_SANDBOX_PROVIDER to one of {', '.join(sorted(BACKEND_SANDBOX_PROVIDERS))}.",
                id="plugin_marketplace.E021",
            )
        )
    if provider == BACKEND_SANDBOX_PROVIDER_EXTERNAL and not external_endpoint.startswith("https://"):
        errors.append(
            Error(
                "Plugin Marketplace external backend sandbox endpoint must be HTTPS.",
                hint="Set PLUGIN_MARKETPLACE_EXTERNAL_BACKEND_SANDBOX_ENDPOINT to the trusted sandbox worker pool endpoint.",
                id="plugin_marketplace.E022",
            )
        )
    if (
        not settings.DEBUG
        and allow_sandboxed_code
        and backend_sandbox
        and frontend_sandbox
        and provider not in {BACKEND_SANDBOX_PROVIDER_EXTERNAL, BACKEND_SANDBOX_PROVIDER_DOCKER}
    ):
        errors.append(
            Error(
                "Plugin Marketplace production backend code must use an isolated runner provider.",
                hint=(
                    "Set PLUGIN_MARKETPLACE_BACKEND_SANDBOX_PROVIDER to external_worker with an HTTPS endpoint "
                    "or docker_runner with the filtered Docker proxy."
                ),
                id="plugin_marketplace.E023",
            )
        )
    errors.extend(_docker_backend_runner_errors(provider=provider, runner_image=runner_image, docker_host=docker_host))
    return errors


@register(Tags.security, deploy=True)
def plugin_marketplace_deploy_check(app_configs, **kwargs):
    errors = []
    release_mode = plugin_marketplace_release_mode()
    signing_provider = str(getattr(settings, "PLUGIN_MARKETPLACE_SIGNING_PROVIDER", "local_hmac") or "").strip()
    signing_keys = getattr(settings, "PLUGIN_MARKETPLACE_SIGNING_KEYS", {}) or {}
    require_keys = bool(getattr(settings, "PLUGIN_MARKETPLACE_REQUIRE_CONFIGURED_SIGNING_KEYS", not settings.DEBUG))
    require_external_signing = bool(
        getattr(settings, "PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SIGNING_PROVIDER", not settings.DEBUG)
    )
    default_key_id = str(getattr(settings, "PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID", "") or "").strip()
    external_sign_endpoint = str(getattr(settings, "PLUGIN_MARKETPLACE_EXTERNAL_SIGNING_ENDPOINT", "") or "").strip()
    external_verify_endpoint = str(getattr(settings, "PLUGIN_MARKETPLACE_EXTERNAL_VERIFY_ENDPOINT", "") or "").strip()
    security_scan_provider = str(
        getattr(settings, "PLUGIN_MARKETPLACE_SECURITY_SCAN_PROVIDER", "local_static") or ""
    ).strip()
    require_external_scanner = bool(getattr(settings, "PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SECURITY_SCANNER", False))
    external_scanner_endpoint = str(
        getattr(settings, "PLUGIN_MARKETPLACE_EXTERNAL_SECURITY_SCAN_ENDPOINT", "") or ""
    ).strip()
    allow_sandboxed_code = bool(getattr(settings, "PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES", False))
    backend_sandbox = bool(getattr(settings, "PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED", False))
    frontend_sandbox = bool(getattr(settings, "PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED", False))
    allow_dynamic_frontend_bundles = bool(getattr(settings, "PLUGIN_MARKETPLACE_ALLOW_DYNAMIC_FRONTEND_BUNDLES", False))
    frontend_bundle_provider = str(
        getattr(settings, "PLUGIN_MARKETPLACE_FRONTEND_BUNDLE_DISTRIBUTION_PROVIDER", "manifest_url") or ""
    ).strip()
    require_external_frontend_bundle_host = bool(
        getattr(settings, "PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_FRONTEND_BUNDLE_HOST", False)
    )
    external_frontend_bundle_endpoint = str(
        getattr(settings, "PLUGIN_MARKETPLACE_EXTERNAL_FRONTEND_BUNDLE_ENDPOINT", "") or ""
    ).strip()
    frontend_bundle_hosts = getattr(settings, "PLUGIN_MARKETPLACE_FRONTEND_BUNDLE_ALLOWED_HOSTS", []) or []
    backend_sandbox_provider = str(
        getattr(settings, "PLUGIN_MARKETPLACE_BACKEND_SANDBOX_PROVIDER", BACKEND_SANDBOX_PROVIDER_DISABLED) or ""
    ).strip()
    external_backend_sandbox_endpoint = str(
        getattr(settings, "PLUGIN_MARKETPLACE_EXTERNAL_BACKEND_SANDBOX_ENDPOINT", "") or ""
    ).strip()
    plugin_backend_runner_image = str(getattr(settings, "PLUGIN_BACKEND_RUNNER_IMAGE", "") or "").strip()
    plugin_backend_docker_host = str(getattr(settings, "PLUGIN_BACKEND_DOCKER_HOST", "") or "").strip()
    compatibility_isolation_mode = str(
        getattr(settings, "PLUGIN_MARKETPLACE_COMPATIBILITY_JOB_ISOLATION_MODE", "in_process_no_code") or ""
    ).strip()
    remote_hosts = getattr(settings, "PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS", []) or []
    catalog_source_hosts = getattr(settings, "PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS", []) or []
    dependency_allowlist = getattr(settings, "PLUGIN_MARKETPLACE_SANDBOX_DEPENDENCY_ALLOWLIST", []) or []
    required_attestation_kinds = getattr(settings, "PLUGIN_MARKETPLACE_REQUIRED_ATTESTATION_KINDS", []) or []
    valid_signing_providers = {"local_hmac", "external_kms"}
    valid_security_scan_providers = {"local_static", "external"}
    valid_frontend_bundle_providers = {"manifest_url", "external_artifact_host"}

    if release_mode not in PLUGIN_MARKETPLACE_RELEASE_MODES:
        errors.append(
            Error(
                "Plugin Marketplace release mode is unknown.",
                hint="Set PLUGIN_MARKETPLACE_RELEASE_MODE to disabled or enabled.",
                id="plugin_marketplace.E030",
            )
        )
        return errors

    if release_mode == PLUGIN_MARKETPLACE_MODE_DISABLED:
        active_runtime_flags = [
            name
            for name, active in (
                ("PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES", allow_sandboxed_code),
                ("PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED", backend_sandbox),
                ("PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED", frontend_sandbox),
                ("PLUGIN_MARKETPLACE_ALLOW_DYNAMIC_FRONTEND_BUNDLES", allow_dynamic_frontend_bundles),
            )
            if active
        ]
        if active_runtime_flags:
            errors.append(
                Error(
                    "Plugin Marketplace is disabled but executable runtime flags are enabled.",
                    hint="Disable: " + ", ".join(active_runtime_flags),
                    id="plugin_marketplace.E031",
                )
            )
        # No plugin routes/providers are registered in this mode, so external
        # signing, scanner and allowlist requirements are outside release scope.
        return errors

    if signing_provider not in valid_signing_providers:
        errors.append(
            Error(
                "Plugin Marketplace signing provider is unknown.",
                hint="Set PLUGIN_MARKETPLACE_SIGNING_PROVIDER to local_hmac or external_kms.",
                id="plugin_marketplace.E004",
            )
        )
    if not settings.DEBUG and require_external_signing and signing_provider != "external_kms":
        errors.append(
            Error(
                "Plugin Marketplace production signing must use an external KMS/HSM provider.",
                hint="Set PLUGIN_MARKETPLACE_SIGNING_PROVIDER=external_kms and configure HTTPS sign/verify endpoints.",
                id="plugin_marketplace.E005",
            )
        )
    if signing_provider == "external_kms":
        if not default_key_id:
            errors.append(
                Error(
                    "Plugin Marketplace external signing key id is not configured.",
                    hint="Set PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID to the external KMS/HSM key alias.",
                    id="plugin_marketplace.E006",
                )
            )
        if not external_sign_endpoint.startswith("https://"):
            errors.append(
                Error(
                    "Plugin Marketplace external signing endpoint must be HTTPS.",
                    hint="Set PLUGIN_MARKETPLACE_EXTERNAL_SIGNING_ENDPOINT to a trusted HTTPS signing endpoint.",
                    id="plugin_marketplace.E007",
                )
            )
        if not external_verify_endpoint.startswith("https://"):
            errors.append(
                Error(
                    "Plugin Marketplace external signature verification endpoint must be HTTPS.",
                    hint="Set PLUGIN_MARKETPLACE_EXTERNAL_VERIFY_ENDPOINT to a trusted HTTPS verification endpoint.",
                    id="plugin_marketplace.E008",
                )
            )
    if signing_provider == "local_hmac" and not settings.DEBUG and require_keys and not signing_keys:
        errors.append(
            Error(
                "Plugin Marketplace signing keys are not configured while DEBUG=False.",
                hint="Set PLUGIN_MARKETPLACE_SIGNING_KEYS to a JSON object and PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID.",
                id="plugin_marketplace.E001",
            )
        )
    if signing_provider == "local_hmac" and default_key_id and default_key_id not in signing_keys:
        errors.append(
            Error(
                "Plugin Marketplace default signing key id is not present in configured signing keys.",
                hint="Set PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID to one key from PLUGIN_MARKETPLACE_SIGNING_KEYS.",
                id="plugin_marketplace.E002",
            )
        )
    if security_scan_provider not in valid_security_scan_providers:
        errors.append(
            Error(
                "Plugin Marketplace security scan provider is unknown.",
                hint="Set PLUGIN_MARKETPLACE_SECURITY_SCAN_PROVIDER to local_static or external.",
                id="plugin_marketplace.E009",
            )
        )
    if not settings.DEBUG and require_external_scanner and security_scan_provider != "external":
        errors.append(
            Error(
                "Plugin Marketplace production security scanning must use an external malware/SCA provider.",
                hint="Set PLUGIN_MARKETPLACE_SECURITY_SCAN_PROVIDER=external and configure PLUGIN_MARKETPLACE_EXTERNAL_SECURITY_SCAN_ENDPOINT.",
                id="plugin_marketplace.E010",
            )
        )
    if security_scan_provider == "external" and not external_scanner_endpoint.startswith("https://"):
        errors.append(
            Error(
                "Plugin Marketplace external security scanner endpoint must be HTTPS.",
                hint="Set PLUGIN_MARKETPLACE_EXTERNAL_SECURITY_SCAN_ENDPOINT to a trusted HTTPS scanner endpoint.",
                id="plugin_marketplace.E011",
            )
        )
    if allow_sandboxed_code and not (backend_sandbox and frontend_sandbox):
        errors.append(
            Error(
                "Plugin Marketplace sandboxed code packages are allowed but both sandbox runtimes are not enabled.",
                hint="Enable PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED and PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED before accepting code packages.",
                id="plugin_marketplace.E015",
            )
        )
    if allow_dynamic_frontend_bundles and not (allow_sandboxed_code and frontend_sandbox):
        errors.append(
            Error(
                "Plugin Marketplace dynamic frontend bundles require sandboxed package support and frontend sandboxing.",
                hint=(
                    "Enable PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES and "
                    "PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED before allowing dynamic frontend bundles."
                ),
                id="plugin_marketplace.E024",
            )
        )
    if frontend_bundle_provider not in valid_frontend_bundle_providers:
        errors.append(
            Error(
                "Plugin Marketplace frontend bundle distribution provider is unknown.",
                hint=(
                    "Set PLUGIN_MARKETPLACE_FRONTEND_BUNDLE_DISTRIBUTION_PROVIDER to "
                    "manifest_url or external_artifact_host."
                ),
                id="plugin_marketplace.E026",
            )
        )
    if not settings.DEBUG and allow_dynamic_frontend_bundles and frontend_bundle_provider != "external_artifact_host":
        errors.append(
            Error(
                "Plugin Marketplace production dynamic frontend bundle distribution must use an external artifact host.",
                hint=(
                    "Set PLUGIN_MARKETPLACE_FRONTEND_BUNDLE_DISTRIBUTION_PROVIDER=external_artifact_host "
                    "and configure the HTTPS readiness endpoint."
                ),
                id="plugin_marketplace.E027",
            )
        )
    if frontend_bundle_provider == "external_artifact_host" and not external_frontend_bundle_endpoint.startswith(
        "https://"
    ):
        errors.append(
            Error(
                "Plugin Marketplace external frontend bundle artifact host endpoint must be HTTPS.",
                hint="Set PLUGIN_MARKETPLACE_EXTERNAL_FRONTEND_BUNDLE_ENDPOINT to the trusted artifact host readiness endpoint.",
                id="plugin_marketplace.E028",
            )
        )
    if (
        (not settings.DEBUG and allow_dynamic_frontend_bundles)
        or require_external_frontend_bundle_host
        or frontend_bundle_provider == "external_artifact_host"
    ) and not frontend_bundle_hosts:
        errors.append(
            Error(
                "Plugin Marketplace frontend bundle host allowlist is empty.",
                hint="Set PLUGIN_MARKETPLACE_FRONTEND_BUNDLE_ALLOWED_HOSTS to trusted bundle CDN/artifact hosts.",
                id="plugin_marketplace.E029",
            )
        )
    errors.extend(
        _backend_sandbox_provider_errors(
            provider=backend_sandbox_provider,
            external_endpoint=external_backend_sandbox_endpoint,
            runner_image=plugin_backend_runner_image,
            docker_host=plugin_backend_docker_host,
            allow_sandboxed_code=allow_sandboxed_code,
            backend_sandbox=backend_sandbox,
            frontend_sandbox=frontend_sandbox,
        )
    )
    invalid_dependencies = invalid_dependency_allowlist_entries(dependency_allowlist)
    if invalid_dependencies:
        errors.append(
            Error(
                "Plugin Marketplace sandbox dependency allowlist contains invalid entries.",
                hint="Use ecosystem:name entries such as python:requests or npm:@scope/package.",
                id="plugin_marketplace.E017",
            )
        )
    if compatibility_isolation_mode not in COMPATIBILITY_JOB_ISOLATION_MODES:
        errors.append(
            Error(
                "Plugin Marketplace compatibility job isolation mode is unknown.",
                hint=(
                    "Set PLUGIN_MARKETPLACE_COMPATIBILITY_JOB_ISOLATION_MODE to "
                    f"one of {', '.join(sorted(COMPATIBILITY_JOB_ISOLATION_MODES))}."
                ),
                id="plugin_marketplace.E018",
            )
        )
    if compatibility_isolation_mode == "subprocess_sandbox" and not (allow_sandboxed_code and backend_sandbox):
        errors.append(
            Error(
                "Plugin Marketplace sandbox compatibility jobs require sandboxed code package support.",
                hint=(
                    "Enable PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES and "
                    "PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED before using subprocess_sandbox jobs."
                ),
                id="plugin_marketplace.E019",
            )
        )
    invalid_attestation_kinds = invalid_required_attestation_kinds(required_attestation_kinds)
    if invalid_attestation_kinds:
        errors.append(
            Error(
                "Plugin Marketplace required attestation kinds contain invalid entries.",
                hint="Use lowercase attestation kind ids such as security_scan or remote_provenance_replay.",
                id="plugin_marketplace.E020",
            )
        )
    if (
        not settings.DEBUG
        and allow_dynamic_frontend_bundles
        and FRONTEND_BUNDLE_REVIEW_ATTESTATION_KIND not in required_attestation_kinds
    ):
        errors.append(
            Error(
                "Plugin Marketplace dynamic frontend bundles require frontend bundle review attestations in production.",
                hint=(
                    "Add frontend_bundle_review to PLUGIN_MARKETPLACE_REQUIRED_ATTESTATION_KINDS before enabling "
                    "PLUGIN_MARKETPLACE_ALLOW_DYNAMIC_FRONTEND_BUNDLES with DEBUG=False."
                ),
                id="plugin_marketplace.E025",
            )
        )
    if not settings.DEBUG and not remote_hosts:
        errors.append(
            Error(
                "Plugin Marketplace remote package host allowlist is empty while DEBUG=False.",
                hint="Set PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS to the trusted package host list.",
                id="plugin_marketplace.E003",
            )
        )
    if not settings.DEBUG and not catalog_source_hosts:
        errors.append(
            Error(
                "Plugin Marketplace federated catalog source host allowlist is empty while DEBUG=False.",
                hint="Set PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS to the trusted catalog host list.",
                id="plugin_marketplace.E016",
            )
        )
    return errors
