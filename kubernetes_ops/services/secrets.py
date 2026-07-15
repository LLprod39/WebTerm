from __future__ import annotations

import os
from collections.abc import Mapping

from django.conf import settings

from core_ui.managed_secrets import get_kubernetes_provider_token
from kubernetes_ops.models import K8sProvider


class KubernetesSecretError(ValueError):
    pass


def managed_provider_secret_ref(provider_id: int) -> str:
    return f"managed:kubernetes-provider-token:{int(provider_id)}"


def resolve_provider_token(provider: K8sProvider) -> str:
    if provider.auth_mode == K8sProvider.AUTH_NONE:
        return ""
    ref = (provider.secret_ref or "").strip()
    if not ref:
        raise KubernetesSecretError(f"{provider.name} provider secret_ref is not configured.")
    if ref.startswith("env:"):
        env_name = ref.removeprefix("env:").strip()
        token = os.environ.get(env_name, "")
        if not token:
            raise KubernetesSecretError(f"{provider.name} provider env secret is missing: {env_name}")
        return token
    if ref.startswith("managed:kubernetes-provider-token:"):
        if ref != managed_provider_secret_ref(provider.id):
            raise KubernetesSecretError(f"{provider.name} provider managed secret reference does not match provider id.")
        token = get_kubernetes_provider_token(provider.id)
        if not token:
            raise KubernetesSecretError(f"{provider.name} provider managed secret is missing.")
        return token

    configured = getattr(settings, "KUBERNETES_OPS_SECRET_VALUES", {})
    if isinstance(configured, Mapping):
        token = str(configured.get(ref) or "")
        if token:
            return token
    raise KubernetesSecretError(f"{provider.name} provider secret reference cannot be resolved.")


def redact_secret(value: object, secret: str = "") -> str:
    text = str(value)
    if secret:
        text = text.replace(secret, "***")
    return text
