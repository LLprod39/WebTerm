from __future__ import annotations

import json
import os
from pathlib import Path

from .env_helpers import env_bool, env_int, env_list


def _json_object_env(name: str) -> dict[str, str]:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): str(value) for key, value in parsed.items() if str(value)}


def build_plugin_marketplace_settings(*, debug: bool) -> dict[str, object]:
    signing_keys = _json_object_env("PLUGIN_MARKETPLACE_SIGNING_KEYS")
    external_backend_endpoint = (os.getenv("PLUGIN_MARKETPLACE_EXTERNAL_BACKEND_SANDBOX_ENDPOINT", "") or "").strip()
    backend_provider_default = "local_subprocess" if debug else "disabled"
    return {
        # The first production release keeps plugin execution out of scope until
        # the external signing/scanning/isolation trust stack is provisioned.
        # Development remains enabled so the existing implementation is testable.
        "PLUGIN_MARKETPLACE_RELEASE_MODE": (
            os.getenv(
                "PLUGIN_MARKETPLACE_RELEASE_MODE",
                "enabled" if debug else "disabled",
            )
            or ("enabled" if debug else "disabled")
        )
        .strip()
        .lower(),
        "PLUGIN_MARKETPLACE_SIGNING_PROVIDER": (
            os.getenv("PLUGIN_MARKETPLACE_SIGNING_PROVIDER", "local_hmac") or "local_hmac"
        ).strip(),
        "PLUGIN_MARKETPLACE_SIGNING_KEYS": signing_keys,
        "PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID": (
            os.getenv("PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID", "") or ""
        ).strip(),
        "PLUGIN_MARKETPLACE_REQUIRE_CONFIGURED_SIGNING_KEYS": env_bool(
            "PLUGIN_MARKETPLACE_REQUIRE_CONFIGURED_SIGNING_KEYS",
            not debug,
        ),
        "PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SIGNING_PROVIDER": env_bool(
            "PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SIGNING_PROVIDER",
            not debug,
        ),
        "PLUGIN_MARKETPLACE_EXTERNAL_SIGNING_ENDPOINT": (
            os.getenv("PLUGIN_MARKETPLACE_EXTERNAL_SIGNING_ENDPOINT", "") or ""
        ).strip(),
        "PLUGIN_MARKETPLACE_EXTERNAL_VERIFY_ENDPOINT": (
            os.getenv("PLUGIN_MARKETPLACE_EXTERNAL_VERIFY_ENDPOINT", "") or ""
        ).strip(),
        "PLUGIN_MARKETPLACE_EXTERNAL_SIGNING_AUTH_TOKEN": (
            os.getenv("PLUGIN_MARKETPLACE_EXTERNAL_SIGNING_AUTH_TOKEN", "") or ""
        ).strip(),
        "PLUGIN_MARKETPLACE_EXTERNAL_SIGNING_TIMEOUT_SECONDS": env_int(
            "PLUGIN_MARKETPLACE_EXTERNAL_SIGNING_TIMEOUT_SECONDS",
            5,
        ),
        "PLUGIN_MARKETPLACE_COMPATIBILITY_JOB_ISOLATION_MODE": (
            os.getenv("PLUGIN_MARKETPLACE_COMPATIBILITY_JOB_ISOLATION_MODE", "in_process_no_code")
            or "in_process_no_code"
        ).strip(),
        "PLUGIN_MARKETPLACE_COMPATIBILITY_JOB_TIMEOUT_SECONDS": env_int(
            "PLUGIN_MARKETPLACE_COMPATIBILITY_JOB_TIMEOUT_SECONDS",
            20,
        ),
        "PLUGIN_MARKETPLACE_SECURITY_SCAN_PROVIDER": (
            os.getenv("PLUGIN_MARKETPLACE_SECURITY_SCAN_PROVIDER", "local_static") or "local_static"
        ).strip(),
        "PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SECURITY_SCANNER": env_bool(
            "PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SECURITY_SCANNER",
            not debug,
        ),
        "PLUGIN_MARKETPLACE_EXTERNAL_SECURITY_SCAN_ENDPOINT": (
            os.getenv("PLUGIN_MARKETPLACE_EXTERNAL_SECURITY_SCAN_ENDPOINT", "") or ""
        ).strip(),
        "PLUGIN_MARKETPLACE_EXTERNAL_SECURITY_SCAN_AUTH_TOKEN": (
            os.getenv("PLUGIN_MARKETPLACE_EXTERNAL_SECURITY_SCAN_AUTH_TOKEN", "") or ""
        ).strip(),
        "PLUGIN_MARKETPLACE_EXTERNAL_SECURITY_SCAN_TIMEOUT_SECONDS": env_int(
            "PLUGIN_MARKETPLACE_EXTERNAL_SECURITY_SCAN_TIMEOUT_SECONDS",
            20,
        ),
        "PLUGIN_MARKETPLACE_SECURITY_SCAN_BLOCK_SEVERITIES": env_list(
            "PLUGIN_MARKETPLACE_SECURITY_SCAN_BLOCK_SEVERITIES",
            ["critical", "high"],
        ),
        "PLUGIN_MARKETPLACE_SECURITY_SCAN_PASS_STATUSES": env_list(
            "PLUGIN_MARKETPLACE_SECURITY_SCAN_PASS_STATUSES",
            ["clean", "ok", "pass", "passed", "success"],
        ),
        "PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED": env_bool(
            "PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED",
            False,
        ),
        "PLUGIN_MARKETPLACE_BACKEND_SANDBOX_PROVIDER": (
            os.getenv("PLUGIN_MARKETPLACE_BACKEND_SANDBOX_PROVIDER", backend_provider_default)
            or backend_provider_default
        ).strip(),
        "PLUGIN_MARKETPLACE_EXTERNAL_BACKEND_SANDBOX_ENDPOINT": external_backend_endpoint,
        "PLUGIN_MARKETPLACE_EXTERNAL_BACKEND_SANDBOX_AUTH_TOKEN": (
            os.getenv("PLUGIN_MARKETPLACE_EXTERNAL_BACKEND_SANDBOX_AUTH_TOKEN", "") or ""
        ).strip(),
        "PLUGIN_MARKETPLACE_BACKEND_SANDBOX_TIMEOUT_SECONDS": env_int(
            "PLUGIN_MARKETPLACE_BACKEND_SANDBOX_TIMEOUT_SECONDS",
            10,
        ),
        "PLUGIN_MARKETPLACE_BACKEND_SANDBOX_MAX_OUTPUT_BYTES": env_int(
            "PLUGIN_MARKETPLACE_BACKEND_SANDBOX_MAX_OUTPUT_BYTES",
            256 * 1024,
        ),
        "PLUGIN_BACKEND_RUNNER_IMAGE": (os.getenv("PLUGIN_BACKEND_RUNNER_IMAGE", "") or "").strip(),
        "PLUGIN_BACKEND_DOCKER_HOST": (os.getenv("PLUGIN_BACKEND_DOCKER_HOST", "") or "").strip(),
        "PLUGIN_BACKEND_DOCKER_COMMAND": (os.getenv("PLUGIN_BACKEND_DOCKER_COMMAND", "docker") or "docker").strip(),
        "PLUGIN_BACKEND_DOCKER_EGRESS_NETWORK": (os.getenv("PLUGIN_BACKEND_DOCKER_EGRESS_NETWORK", "") or "").strip(),
        "PLUGIN_BACKEND_DOCKER_CPUS": (os.getenv("PLUGIN_BACKEND_DOCKER_CPUS", "0.5") or "0.5").strip(),
        "PLUGIN_BACKEND_DOCKER_MEMORY": (os.getenv("PLUGIN_BACKEND_DOCKER_MEMORY", "128m") or "128m").strip(),
        "PLUGIN_BACKEND_DOCKER_PIDS_LIMIT": env_int("PLUGIN_BACKEND_DOCKER_PIDS_LIMIT", 32),
        "PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED": env_bool(
            "PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED",
            False,
        ),
        "PLUGIN_MARKETPLACE_ALLOW_DYNAMIC_FRONTEND_BUNDLES": env_bool(
            "PLUGIN_MARKETPLACE_ALLOW_DYNAMIC_FRONTEND_BUNDLES",
            False,
        ),
        "PLUGIN_MARKETPLACE_FRONTEND_BUNDLE_DISTRIBUTION_PROVIDER": (
            os.getenv("PLUGIN_MARKETPLACE_FRONTEND_BUNDLE_DISTRIBUTION_PROVIDER", "manifest_url") or "manifest_url"
        ).strip(),
        "PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_FRONTEND_BUNDLE_HOST": env_bool(
            "PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_FRONTEND_BUNDLE_HOST",
            False,
        ),
        "PLUGIN_MARKETPLACE_EXTERNAL_FRONTEND_BUNDLE_ENDPOINT": (
            os.getenv("PLUGIN_MARKETPLACE_EXTERNAL_FRONTEND_BUNDLE_ENDPOINT", "") or ""
        ).strip(),
        "PLUGIN_MARKETPLACE_EXTERNAL_FRONTEND_BUNDLE_AUTH_TOKEN": (
            os.getenv("PLUGIN_MARKETPLACE_EXTERNAL_FRONTEND_BUNDLE_AUTH_TOKEN", "") or ""
        ).strip(),
        "PLUGIN_MARKETPLACE_EXTERNAL_FRONTEND_BUNDLE_TIMEOUT_SECONDS": env_int(
            "PLUGIN_MARKETPLACE_EXTERNAL_FRONTEND_BUNDLE_TIMEOUT_SECONDS",
            10,
        ),
        "PLUGIN_MARKETPLACE_FRONTEND_BUNDLE_ALLOWED_HOSTS": env_list(
            "PLUGIN_MARKETPLACE_FRONTEND_BUNDLE_ALLOWED_HOSTS"
        ),
        "PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES": env_bool(
            "PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES",
            False,
        ),
        "PLUGIN_MARKETPLACE_SANDBOX_DEPENDENCY_ALLOWLIST": env_list("PLUGIN_MARKETPLACE_SANDBOX_DEPENDENCY_ALLOWLIST"),
        "PLUGIN_MARKETPLACE_EGRESS_DENIED_HOSTS": env_list("PLUGIN_MARKETPLACE_EGRESS_DENIED_HOSTS"),
        "PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS": env_list("PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS"),
        "PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS": env_list("PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS"),
        "PLUGIN_MARKETPLACE_PACKAGE_RETENTION_DIR": (
            Path(os.getenv("PLUGIN_MARKETPLACE_PACKAGE_RETENTION_DIR")).expanduser()
            if os.getenv("PLUGIN_MARKETPLACE_PACKAGE_RETENTION_DIR")
            else None
        ),
        "PLUGIN_MARKETPLACE_RETAINED_PACKAGE_MAX_AGE_DAYS": env_int(
            "PLUGIN_MARKETPLACE_RETAINED_PACKAGE_MAX_AGE_DAYS",
            0,
        ),
        "PLUGIN_MARKETPLACE_ATTESTATION_RETENTION_LIMIT": env_int(
            "PLUGIN_MARKETPLACE_ATTESTATION_RETENTION_LIMIT",
            20,
        ),
        "PLUGIN_MARKETPLACE_REQUIRED_ATTESTATION_KINDS": env_list("PLUGIN_MARKETPLACE_REQUIRED_ATTESTATION_KINDS"),
        "PLUGIN_MARKETPLACE_ATTESTATION_MAX_AGE_DAYS": env_int(
            "PLUGIN_MARKETPLACE_ATTESTATION_MAX_AGE_DAYS",
            0,
        ),
    }
