from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_ui.settings.production")

import django  # noqa: E402

django.setup()

from django.contrib.auth.models import User  # noqa: E402
from django.db import connection  # noqa: E402

from core_ui.managed_secrets import list_undecryptable_secrets, verify_managed_secret_roundtrip  # noqa: E402
from core_ui.models import ManagedSecret, UserActivityLog  # noqa: E402
from servers.models import AgentRun, Server  # noqa: E402
from studio.models import Pipeline, PipelineRun  # noqa: E402


def _digest_rows(rows: Iterable[Iterable[Any]]) -> dict[str, Any]:
    normalized = [list(row) for row in rows]
    payload = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), default=str).encode()
    return {"count": len(normalized), "sha256": hashlib.sha256(payload).hexdigest()}


def _volume_digest(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    file_count = 0
    total_bytes = 0
    if not path.exists():
        return {"exists": False, "files": 0, "bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()}
    for candidate in sorted(item for item in path.rglob("*") if item.is_file() or item.is_symlink()):
        relative = candidate.relative_to(path).as_posix()
        content = os.readlink(candidate).encode() if candidate.is_symlink() else candidate.read_bytes()
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(content).digest())
        file_count += 1
        total_bytes += len(content)
    return {"exists": True, "files": file_count, "bytes": total_bytes, "sha256": digest.hexdigest()}


def _plugin_package_rows() -> list[tuple[Any, ...]]:
    table_name = "plugin_marketplace_pluginpackage"
    if table_name not in connection.introspection.table_names():
        return []
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT id, plugin_id, version, package_hash, review_status, signature_status "
            f'FROM "{table_name}" ORDER BY id'
        )
        return list(cursor.fetchall())


def build_manifest(*, auth_username: str, auth_password: str) -> dict[str, Any]:
    password_valid = False
    auth_user = User.objects.filter(username=auth_username).first()
    if auth_user is not None and auth_password:
        password_valid = auth_user.check_password(auth_password)

    tables = {
        "auth_users": _digest_rows(
            User.objects.order_by("id").values_list("id", "username", "email", "is_active", "is_staff", "is_superuser")
        ),
        "servers": _digest_rows(
            Server.objects.order_by("id").values_list(
                "id", "user_id", "name", "host", "port", "username", "auth_method", "is_active"
            )
        ),
        "pipelines": _digest_rows(
            Pipeline.objects.order_by("id").values_list(
                "id", "owner_id", "name", "graph_version", "is_shared", "is_template"
            )
        ),
        "pipeline_runs": _digest_rows(
            PipelineRun.objects.order_by("id").values_list(
                "id", "pipeline_id", "triggered_by_id", "status", "started_at", "finished_at"
            )
        ),
        "agent_runs": _digest_rows(
            AgentRun.objects.order_by("id").values_list(
                "id", "agent_id", "server_id", "user_id", "status", "duration_ms", "completed_at"
            )
        ),
        "audit_events": _digest_rows(
            UserActivityLog.objects.order_by("id").values_list(
                "id", "user_id", "category", "action", "status", "entity_type", "entity_id", "created_at"
            )
        ),
        "plugin_packages": _digest_rows(_plugin_package_rows()),
        "managed_secrets": _digest_rows(
            ManagedSecret.objects.order_by("id").values_list(
                "id", "namespace", "object_id", "key", "ciphertext", "metadata"
            )
        ),
    }
    required_nonempty = (
        "auth_users",
        "servers",
        "pipelines",
        "pipeline_runs",
        "agent_runs",
        "audit_events",
        "managed_secrets",
    )
    empty_required = [name for name in required_nonempty if tables[name]["count"] == 0]
    undecryptable = list_undecryptable_secrets()
    return {
        "schema_version": 1,
        "database": tables,
        "authentication": {
            "user_present": auth_user is not None,
            "password_valid": password_valid,
            "username_sha256": hashlib.sha256(auth_username.encode()).hexdigest(),
        },
        "managed_secret_envelopes": {
            "roundtrip": verify_managed_secret_roundtrip(),
            "all_decryptable": not undecryptable,
            "undecryptable_count": len(undecryptable),
        },
        "required_nonempty": not empty_required,
        "volumes": {
            "config": _volume_digest(Path("/workspace/config_runtime")),
            "media": _volume_digest(Path("/workspace/media")),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a privacy-safe WebTerm recovery integrity manifest")
    parser.add_argument("--auth-username", required=True)
    args = parser.parse_args()
    password = os.environ.get("RECOVERY_AUTH_PASSWORD", "")
    manifest = build_manifest(auth_username=args.auth_username, auth_password=password)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    if not manifest["required_nonempty"]:
        return 1
    if not all(manifest["authentication"].values()):
        return 1
    envelopes = manifest["managed_secret_envelopes"]
    if not envelopes["roundtrip"] or not envelopes["all_decryptable"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
