from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Iterable
from typing import Any

sys.path.insert(0, "/workspace")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_ui.settings.production")

import django  # noqa: E402

django.setup()

from django.apps import apps  # noqa: E402

from core_ui.managed_secrets import list_undecryptable_secrets, verify_managed_secret_roundtrip  # noqa: E402


def _digest_rows(rows: Iterable[Iterable[Any]]) -> dict[str, Any]:
    normalized = [list(row) for row in rows]
    payload = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), default=str).encode()
    return {"count": len(normalized), "sha256": hashlib.sha256(payload).hexdigest()}


def _rows(app_label: str, model_name: str, fields: tuple[str, ...]) -> dict[str, Any]:
    model = apps.get_model(app_label, model_name)
    return _digest_rows(model.objects.order_by("id").values_list(*fields))


def main() -> int:
    username = os.environ.get("LIFECYCLE_AUTH_USERNAME", "lifecycle-user-01")
    password = os.environ.get("LIFECYCLE_AUTH_PASSWORD", "")
    user_model = apps.get_model("auth", "User")
    user = user_model.objects.filter(username=username).first()
    password_valid = bool(user is not None and password and user.check_password(password))
    undecryptable = list_undecryptable_secrets()
    tables = {
        "auth_users": _rows(
            "auth",
            "User",
            ("id", "username", "email", "is_active", "is_staff", "is_superuser"),
        ),
        "servers": _rows(
            "servers",
            "Server",
            ("id", "user_id", "name", "host", "port", "username", "auth_method", "is_active"),
        ),
        "pipelines": _rows(
            "studio",
            "Pipeline",
            ("id", "owner_id", "name", "is_shared", "is_template"),
        ),
        "managed_secrets": _rows(
            "core_ui",
            "ManagedSecret",
            ("id", "namespace", "object_id", "key", "ciphertext", "metadata"),
        ),
    }
    required_nonempty = all(item["count"] > 0 for item in tables.values())
    payload = {
        "schema_version": 1,
        "database": tables,
        "authentication": {
            "user_present": user is not None,
            "password_valid": password_valid,
            "username_sha256": hashlib.sha256(username.encode()).hexdigest(),
        },
        "managed_secret_envelopes": {
            "roundtrip": verify_managed_secret_roundtrip(),
            "all_decryptable": not undecryptable,
            "undecryptable_count": len(undecryptable),
        },
        "required_nonempty": required_nonempty,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    healthy = (
        required_nonempty
        and password_valid
        and payload["managed_secret_envelopes"]["roundtrip"]
        and payload["managed_secret_envelopes"]["all_decryptable"]
    )
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
