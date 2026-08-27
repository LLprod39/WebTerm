"""Safe manifest/YAML preview, secret detection and export redaction."""

from __future__ import annotations

import hashlib
import json
import re
from ipaddress import ip_address, ip_network
from pathlib import PurePosixPath
from typing import Any

import yaml
from yaml.tokens import AliasToken

from servers.services.playbooks.bundle_archive import (
    CHECKSUMS_NAME,
    MANIFEST_KIND,
    MANIFEST_NAME,
    MANIFEST_SCHEMA_VERSION,
    YAML_EXTENSIONS,
    BundleFile,
    BundleLimits,
    BundleValidationError,
    normalize_bundle_path,
)

MANIFEST_ALLOWED_KEYS = frozenset(
    {
        "description",
        "checksum_algorithm",
        "checksums",
        "checksums_file",
        "entrypoint",
        "kind",
        "name",
        "redaction_count",
        "required_collections",
        "required_roles",
        "revision",
        "sanitized",
        "schema_version",
        "tags",
    }
)
MANIFEST_REVISION_ALLOWED_KEYS = frozenset({"bundle_hash", "content_hash", "id", "number"})

_SENSITIVE_KEY_RE = re.compile(
    r"(?:^|[_-])(api[_-]?key|access[_-]?key|credential|pass|passphrase|password|passwd|private[_-]?key|secret|token)(?:$|[_-])",
    re.IGNORECASE,
)
_INVENTORY_IDENTITY_KEYS = frozenset(
    {
        "ansible_host",
        "ansible_port",
        "ansible_user",
        "group_ids",
        "inventory_bindings",
        "server_ids",
    }
)
_INVENTORY_SECRET_KEYS = frozenset(
    {
        "ansible_become_pass",
        "ansible_become_password",
        "ansible_password",
        "ansible_private_key",
        "ansible_private_key_file",
        "ansible_ssh_pass",
        "ansible_ssh_passphrase",
        "ansible_ssh_password",
        "ansible_ssh_private_key_file",
        "ansible_sudo_pass",
        "ansible_winrm_password",
    }
)
_SUSPICIOUS_FILE_RE = re.compile(
    r"(?:^|/)(?:\.env(?:\..*)?|.*(?:binding|credential|inventory|password|private[_-]?key|secret|token|vault).*)$",
    re.IGNORECASE,
)
_PRIVATE_KEY_BLOCK_RE = re.compile(
    r"(?:-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----.*?"
    r"-----END (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----|"
    r"-----BEGIN PGP PRIVATE KEY BLOCK-----.*?-----END PGP PRIVATE KEY BLOCK-----|"
    r"^PuTTY-User-Key-File-[0-9]+:.*?^Private-Lines:\s*[0-9]+\s*$.*?(?=^Private-MAC:|\Z))",
    re.DOTALL | re.MULTILINE,
)
_ASSIGNMENT_RE = re.compile(
    r"(?im)^(?P<prefix>\s*[\"']?(?P<key>[A-Za-z_][A-Za-z0-9_-]{0,100})[\"']?\s*[:=]\s*)"
    r"(?P<value>[^\r\n#]+)(?P<suffix>\s*(?:#.*)?)$"
)
_TOKEN_PATTERNS = (
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{10,}\b", re.IGNORECASE),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bxox[bpsar]-[0-9A-Za-z-]{10,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"(?i)\b(?:https?|git)://[^/\s:@]+:[^@\s/]+@"),
)

_CHECKSUM_LINE_RE = re.compile(r"^([0-9a-f]{64})  (.+)$")
_INLINE_ASSIGNMENT_RE = re.compile(
    r"(?i)(?P<prefix>[\"']?(?P<key>[A-Za-z_][A-Za-z0-9_-]{0,100})[\"']?\s*[:=]\s*)"
    r"(?:(?P<quote>[\"'])(?P<quoted_value>[^\r\n]{1,1000}?)(?P=quote)|"
    r"(?P<bare_value>[A-Za-z0-9._~+/=-]{4,1000}))"
)
_NON_BLOCKING_REFERENCE_FINDINGS = frozenset({"inventory_identity", "suspicious_filename"})
_SENSITIVE_COMPACT_KEYS = frozenset(
    {
        "apikey",
        "accesskey",
        "credential",
        "pass",
        "passphrase",
        "password",
        "passwd",
        "privatekey",
        "secret",
        "token",
    }
)


def _parse_manifest_checksum_metadata(document: dict[str, Any]) -> dict[str, Any]:
    if "checksum_algorithm" not in document and "checksums_file" not in document and "checksums" not in document:
        return {}
    if document.get("checksum_algorithm") != "sha256" or document.get("checksums_file") != "checksums.sha256":
        raise BundleValidationError("Manifest checksum metadata is invalid", code="invalid_manifest")
    checksums = document.get("checksums")
    if not isinstance(checksums, dict) or len(checksums) > 250:
        raise BundleValidationError("Manifest checksums are invalid", code="invalid_manifest")
    normalized_checksums: dict[str, str] = {}
    for raw_path, raw_hash in checksums.items():
        path = normalize_bundle_path(str(raw_path))
        content_hash = str(raw_hash or "").strip().casefold()
        if len(content_hash) != 64 or any(character not in "0123456789abcdef" for character in content_hash):
            raise BundleValidationError("Manifest checksums are invalid", code="invalid_manifest")
        normalized_checksums[path] = content_hash
    return {
        "checksum_algorithm": "sha256",
        "checksums_file": "checksums.sha256",
        "checksums": normalized_checksums,
    }


def parse_manifest(item: BundleFile | None) -> dict[str, Any]:
    if item is None:
        return {}
    document = safe_json_load(item.path, item.content)
    if not isinstance(document, dict):
        raise BundleValidationError("manifest.json must contain an object", code="invalid_manifest")
    unknown = sorted(set(document) - MANIFEST_ALLOWED_KEYS)
    if unknown:
        raise BundleValidationError(
            "manifest.json contains unsupported fields",
            code="invalid_manifest",
            details={"fields": unknown},
        )
    version = document.get("schema_version", MANIFEST_SCHEMA_VERSION)
    if version != MANIFEST_SCHEMA_VERSION:
        raise BundleValidationError("Unsupported bundle manifest schema version", code="invalid_manifest")
    kind = document.get("kind", MANIFEST_KIND)
    if kind != MANIFEST_KIND:
        raise BundleValidationError("Unsupported bundle manifest kind", code="invalid_manifest")

    normalized: dict[str, Any] = {"schema_version": MANIFEST_SCHEMA_VERSION, "kind": MANIFEST_KIND}
    for key in ("name", "description"):
        if key in document:
            value = document[key]
            if not isinstance(value, str) or len(value) > (200 if key == "name" else 2000):
                raise BundleValidationError(f"Manifest {key} is invalid", code="invalid_manifest")
            normalized[key] = value
    if document.get("entrypoint"):
        normalized["entrypoint"] = normalize_bundle_path(document["entrypoint"])
    for key in ("required_collections", "required_roles", "tags"):
        if key in document:
            normalized[key] = _validate_string_list(document[key], key)
    if "revision" in document:
        revision = document["revision"]
        if not isinstance(revision, dict) or set(revision) - MANIFEST_REVISION_ALLOWED_KEYS:
            raise BundleValidationError("Manifest revision metadata is invalid", code="invalid_manifest")
        normalized["revision"] = {
            key: revision[key]
            for key in ("id", "number", "content_hash", "bundle_hash")
            if key in revision and isinstance(revision[key], (str, int))
        }
    if "sanitized" in document:
        normalized["sanitized"] = bool(document["sanitized"])
    if "redaction_count" in document:
        value = document["redaction_count"]
        if not isinstance(value, int) or value < 0:
            raise BundleValidationError("Manifest redaction_count is invalid", code="invalid_manifest")
        normalized["redaction_count"] = value
    normalized.update(_parse_manifest_checksum_metadata(document))
    return normalized


def validate_bundle_checksums(files: dict[str, BundleFile], manifest: dict[str, Any]) -> None:
    """Verify optional export checksums before any source-derived data is trusted."""

    checksums = manifest.get("checksums")
    if checksums is None:
        return
    payload_paths = set(files) - {MANIFEST_NAME, CHECKSUMS_NAME}
    if set(checksums) != payload_paths:
        raise BundleValidationError(
            "Bundle checksum manifest does not cover every payload file",
            code="bundle_checksum_mismatch",
            status_code=422,
        )
    for path in sorted(payload_paths):
        if hashlib.sha256(files[path].content).hexdigest() != checksums[path]:
            raise BundleValidationError(
                "Bundle payload checksum verification failed",
                code="bundle_checksum_mismatch",
                status_code=422,
            )

    checksum_item = files.get(CHECKSUMS_NAME)
    if checksum_item is None:
        raise BundleValidationError(
            "Bundle checksum file is missing",
            code="bundle_checksum_mismatch",
            status_code=422,
        )
    try:
        lines = checksum_item.content.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise BundleValidationError(
            "Bundle checksum file is malformed",
            code="bundle_checksum_mismatch",
            status_code=422,
        ) from exc
    rows: dict[str, str] = {}
    for line in lines:
        match = _CHECKSUM_LINE_RE.fullmatch(line)
        if match is None:
            raise BundleValidationError(
                "Bundle checksum file is malformed",
                code="bundle_checksum_mismatch",
                status_code=422,
            )
        path = normalize_bundle_path(match.group(2))
        if path == CHECKSUMS_NAME or path in rows:
            raise BundleValidationError(
                "Bundle checksum file is malformed",
                code="bundle_checksum_mismatch",
                status_code=422,
            )
        rows[path] = match.group(1)
    expected_paths = set(files) - {CHECKSUMS_NAME}
    if set(rows) != expected_paths:
        raise BundleValidationError(
            "Bundle checksum file does not cover every exported file",
            code="bundle_checksum_mismatch",
            status_code=422,
        )
    for path in sorted(expected_paths):
        if hashlib.sha256(files[path].content).hexdigest() != rows[path]:
            raise BundleValidationError(
                "Bundle checksum file verification failed",
                code="bundle_checksum_mismatch",
                status_code=422,
            )


def safe_json_load(path: str, content: bytes) -> Any:
    try:
        document = json.loads(content.decode("utf-8"))
    except RecursionError as exc:
        raise BundleValidationError(
            "JSON structure is too complex", code="yaml_complexity_limit", status_code=413
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleValidationError(f"JSON is malformed: {path}", code="malformed_json") from exc
    _validate_yaml_complexity(document)
    return document


def safe_yaml_load(path: str, content: bytes, limits: BundleLimits) -> Any:
    text = content.decode("utf-8")
    try:
        alias_count = sum(1 for token in yaml.scan(text, Loader=yaml.SafeLoader) if isinstance(token, AliasToken))
        if alias_count > limits.max_yaml_aliases:
            raise BundleValidationError("YAML alias limit exceeded", code="yaml_complexity_limit", status_code=413)
        document = yaml.safe_load(text)
    except BundleValidationError:
        raise
    except RecursionError as exc:
        raise BundleValidationError(
            "YAML structure is too complex", code="yaml_complexity_limit", status_code=413
        ) from exc
    except yaml.YAMLError as exc:
        raise BundleValidationError(f"YAML is malformed: {path}", code="malformed_yaml") from exc
    _validate_yaml_complexity(document)
    return document


def validate_requirements(documents: dict[str, Any]) -> None:
    for path in ("requirements.yml", "requirements.yaml"):
        if path not in documents:
            continue
        document = documents[path]
        if isinstance(document, list):
            entries = document
        elif isinstance(document, dict) and set(document).issubset({"collections", "roles"}):
            collections = document.get("collections") or []
            roles = document.get("roles") or []
            if not isinstance(collections, list) or not isinstance(roles, list):
                raise BundleValidationError(
                    "requirements.yml dependency groups must be lists",
                    code="malformed_requirements",
                )
            entries = [*collections, *roles]
        else:
            raise BundleValidationError("requirements.yml has an unsupported shape", code="malformed_requirements")
        if len(entries) > 100 or any(not isinstance(item, (str, dict)) for item in entries):
            raise BundleValidationError("requirements.yml contains invalid dependencies", code="malformed_requirements")


def collect_bundle_dependencies(documents: dict[str, Any], manifest: dict[str, Any]) -> dict[str, list[str]]:
    """Merge declared Galaxy dependencies without exposing arbitrary metadata."""

    collections = {str(item)[:200] for item in manifest.get("required_collections") or [] if str(item).strip()}
    roles = {str(item)[:200] for item in manifest.get("required_roles") or [] if str(item).strip()}
    for path in ("requirements.yml", "requirements.yaml"):
        document = documents.get(path)
        if isinstance(document, dict):
            for item in document.get("collections") or []:
                name = _dependency_name(item, kind="collection")
                if name:
                    collections.add(name)
            for item in document.get("roles") or []:
                name = _dependency_name(item, kind="role")
                if name:
                    roles.add(name)
        elif isinstance(document, list):
            for item in document:
                name = _dependency_name(item, kind="role")
                if name:
                    roles.add(name)
    for path, document in documents.items():
        if path in {"requirements.yml", "requirements.yaml"} or not isinstance(document, list):
            continue
        for play in document:
            if not isinstance(play, dict):
                continue
            play_collections = play.get("collections") if isinstance(play.get("collections"), list) else []
            for item in play_collections:
                name = _dependency_name(item, kind="collection")
                if name:
                    collections.add(name)
            play_roles = play.get("roles") if isinstance(play.get("roles"), list) else []
            for item in play_roles:
                name = _dependency_name(item, kind="role")
                if name:
                    roles.add(name)
    return {"collections": sorted(collections)[:100], "roles": sorted(roles)[:100]}


def _dependency_name(item: Any, *, kind: str) -> str:
    if isinstance(item, str):
        return item.strip()[:200]
    if not isinstance(item, dict):
        return ""
    keys = ("name", "source") if kind == "collection" else ("role", "name", "src")
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:200]
    return ""


def build_entrypoint_previews(documents: dict[str, Any]) -> list[dict[str, Any]]:
    previews: list[dict[str, Any]] = []
    for path, document in sorted(documents.items()):
        if ("/" in path and not path.startswith("playbooks/")) or path in {
            "requirements.yml",
            "requirements.yaml",
        }:
            continue
        if not isinstance(document, list) or not document or not all(isinstance(play, dict) for play in document):
            continue
        if not any("hosts" in play or "import_playbook" in play for play in document):
            continue
        plays: list[dict[str, Any]] = []
        task_count = 0
        for play in document:
            count = sum(
                len(play.get(key) or [])
                for key in ("pre_tasks", "tasks", "post_tasks", "handlers")
                if isinstance(play.get(key), list)
            )
            task_count += count
            plays.append(
                {
                    "name": str(play.get("name") or "")[:200],
                    "hosts": _safe_selector_preview(play.get("hosts")),
                    "task_count": count,
                }
            )
        previews.append({"path": path, "play_count": len(plays), "task_count": task_count, "plays": plays})
    return previews


def scan_bundle_secrets(
    files: list[BundleFile],
    yaml_documents: dict[str, Any],
    json_documents: dict[str, Any],
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for item in files:
        if any(
            finding.get("kind") in {"credential_pattern", "private_key", "sensitive_assignment"}
            for finding in _scan_text_for_tokens("bundle-path", item.path)
        ):
            findings.append({"path": "bundle-path", "kind": "credential_path"})
        if _suspicious_path(item.path):
            findings.append({"path": item.path, "kind": "suspicious_filename"})
        text = item.content.decode("utf-8", errors="ignore")
        if text.lstrip().startswith("$ANSIBLE_VAULT;"):
            findings.append({"path": item.path, "kind": "encrypted_vault"})
        findings.extend(_scan_text_for_tokens(item.path, text))
    for path, document in {**yaml_documents, **json_documents}.items():
        findings.extend(_scan_structure_for_secrets(path, document))

    unique: dict[tuple[str, str, str], dict[str, str]] = {}
    for finding in findings:
        key = (finding.get("path", ""), finding.get("kind", ""), finding.get("key", ""))
        unique[key] = finding
    return list(unique.values())


def blocking_secret_findings(findings: Any) -> list[dict[str, str]]:
    """A suspicious reference filename alone is export-redacted, not secret proof."""

    return [
        item
        for item in findings or []
        if isinstance(item, dict) and item.get("kind") not in _NON_BLOCKING_REFERENCE_FINDINGS
    ]


def contains_credential_material(value: str) -> bool:
    """Detect a literal credential value without returning or logging it."""

    return any(
        item.get("kind") in {"credential_pattern", "private_key", "sensitive_assignment"}
        for item in _scan_text_for_tokens("value", str(value or ""))
    )


def sanitize_file_for_export(item: BundleFile) -> tuple[bytes | None, int]:
    if _suspicious_path(item.path):
        return None, 1
    if not item.is_text:
        findings = _scan_text_for_tokens(item.path, item.content.decode("utf-8", errors="ignore"))
        return (None, len(findings)) if findings else (item.content, 0)

    text = item.content.decode("utf-8")
    suffix = PurePosixPath(item.path).suffix.lower()
    redactions = 0
    if suffix in YAML_EXTENSIONS:
        parsed = safe_yaml_load(item.path, item.content, BundleLimits.from_settings())
        parsed, redactions = _redact_structure(parsed)
        if redactions:
            text = yaml.safe_dump(parsed, allow_unicode=True, sort_keys=False)
    elif suffix == ".json":
        parsed = json.loads(text)
        parsed, redactions = _redact_structure(parsed)
        if redactions:
            text = json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    text, plain_redactions = _redact_plain_text(text)
    return text.encode("utf-8"), redactions + plain_redactions


def sanitize_preview_value(value: Any) -> Any:
    """Redact source-derived labels and metadata before returning an unsafe preview."""

    redacted, _count = _redact_structure(value)
    return redacted


def _validate_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 100:
        raise BundleValidationError(f"Manifest {field} must be a bounded list", code="invalid_manifest")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > 200:
            raise BundleValidationError(f"Manifest {field} contains an invalid item", code="invalid_manifest")
        result.append(item.strip())
    return result


def _validate_yaml_complexity(document: Any) -> None:
    stack: list[tuple[Any, int]] = [(document, 0)]
    seen: set[int] = set()
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > 20_000 or depth > 60:
            raise BundleValidationError("YAML structure is too complex", code="yaml_complexity_limit", status_code=413)
        if isinstance(value, dict):
            identity = id(value)
            if identity in seen:
                continue
            seen.add(identity)
            stack.extend((item, depth + 1) for pair in value.items() for item in pair)
        elif isinstance(value, (list, tuple, set)):
            identity = id(value)
            if identity in seen:
                continue
            seen.add(identity)
            stack.extend((item, depth + 1) for item in value)


def _safe_selector_preview(value: Any) -> str:
    if isinstance(value, str):
        return value[:300]
    if isinstance(value, list):
        return ",".join(str(item) for item in value[:20])[:300]
    return ""


def _scan_structure_for_secrets(path: str, document: Any) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    stack = [document]
    seen: set[int] = set()
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            if id(value) in seen:
                continue
            seen.add(id(value))
            for key, nested in value.items():
                key_text = str(key)
                if _is_sensitive_key(key_text) and _contains_secret_value(nested):
                    findings.append({"path": path, "kind": "sensitive_value", "key": key_text[:80]})
                elif _is_inventory_identity_key(key_text) and _contains_secret_value(nested):
                    findings.append({"path": path, "kind": "inventory_identity", "key": key_text[:80]})
                elif key_text.casefold() == "hosts" and _contains_literal_host(nested):
                    findings.append({"path": path, "kind": "inventory_identity", "key": "hosts"})
                stack.append(nested)
        elif isinstance(value, (list, tuple)):
            if id(value) in seen:
                continue
            seen.add(id(value))
            stack.extend(value)
        elif isinstance(value, str):
            findings.extend(_scan_text_for_tokens(path, value))
    return findings


def _contains_secret_value(value: Any) -> bool:
    if value is None or value is False or value == "":
        return False
    if isinstance(value, str):
        stripped = value.strip()
        unquoted = stripped.strip("\"'")
        if not stripped or unquoted in {"__REDACTED__", "<redacted>"}:
            return False
        if (stripped.startswith("{{") and stripped.endswith("}}")) or stripped.startswith(("${", "ref:", "secret://")):
            return False
        if re.fullmatch(r"vault_[A-Za-z0-9_.-]+", stripped):
            return False
    return True


def _scan_text_for_tokens(path: str, text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if _PRIVATE_KEY_BLOCK_RE.search(text):
        findings.append({"path": path, "kind": "private_key"})
    for pattern in _TOKEN_PATTERNS:
        if pattern.search(text):
            findings.append({"path": path, "kind": "credential_pattern"})
    for match in _ASSIGNMENT_RE.finditer(text):
        if _is_inventory_identity_key(match.group("key")):
            findings.append({"path": path, "kind": "inventory_identity", "key": match.group("key")[:80]})
        elif _is_sensitive_key(match.group("key")) and _contains_secret_value(match.group("value").strip().rstrip(",")):
            findings.append({"path": path, "kind": "sensitive_assignment"})
            break
    for match in _INLINE_ASSIGNMENT_RE.finditer(text):
        value = match.group("quoted_value") or match.group("bare_value") or ""
        if _is_inventory_identity_key(match.group("key")):
            findings.append({"path": path, "kind": "inventory_identity", "key": match.group("key")[:80]})
        elif _is_sensitive_key(match.group("key")) and _contains_secret_value(value.strip().rstrip(",")):
            findings.append({"path": path, "kind": "sensitive_assignment"})
            break
    return findings


def _suspicious_path(path: str) -> bool:
    return bool(_SUSPICIOUS_FILE_RE.search(path))


def _redact_structure(value: Any, seen: set[int] | None = None) -> tuple[Any, int]:
    seen = seen if seen is not None else set()
    if isinstance(value, dict):
        if id(value) in seen:
            return "__REDACTED_ALIAS__", 1
        seen.add(id(value))
        output: dict[Any, Any] = {}
        redactions = 0
        for key, nested in value.items():
            if _is_sensitive_key(str(key)) and _contains_secret_value(nested):
                output[key] = "__REDACTED__"
                redactions += 1
            elif (
                _is_inventory_identity_key(str(key))
                and _contains_secret_value(nested)
                or str(key).casefold() in {"hosts", "host_selectors", "missing_bindings"}
                and _contains_literal_host(nested)
            ):
                output[key] = "__REDACTED_TARGET__"
                redactions += 1
            else:
                output[key], count = _redact_structure(nested, seen)
                redactions += count
        return output, redactions
    if isinstance(value, list):
        if id(value) in seen:
            return ["__REDACTED_ALIAS__"], 1
        seen.add(id(value))
        output_list = []
        redactions = 0
        for nested in value:
            redacted, count = _redact_structure(nested, seen)
            output_list.append(redacted)
            redactions += count
        return output_list, redactions
    if isinstance(value, str):
        redacted, count = _redact_plain_text(value)
        return redacted, count
    return value, 0


def _is_sensitive_key(value: str) -> bool:
    snake_case = _normalized_key(value)
    compact = re.sub(r"[^a-z0-9]", "", value.casefold())
    return (
        snake_case in _INVENTORY_SECRET_KEYS
        or bool(_SENSITIVE_KEY_RE.search(snake_case))
        or any(compact.endswith(marker) for marker in _SENSITIVE_COMPACT_KEYS)
    )


def _is_inventory_identity_key(value: str) -> bool:
    return _normalized_key(value) in _INVENTORY_IDENTITY_KEYS


def _normalized_key(value: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value).casefold().replace("-", "_")


def _contains_literal_host(value: Any) -> bool:
    values = value if isinstance(value, list) else [value]
    for item in values:
        if not isinstance(item, str):
            continue
        for token in item.split(","):
            candidate = token.strip()
            try:
                if "/" in candidate:
                    ip_network(candidate, strict=False)
                else:
                    ip_address(candidate)
            except ValueError:
                continue
            return True
    return False


def _redact_plain_text(text: str) -> tuple[str, int]:
    redactions = 0

    def private_key_replacement(_match: re.Match[str]) -> str:
        nonlocal redactions
        redactions += 1
        return "__REDACTED_PRIVATE_KEY__"

    text = _PRIVATE_KEY_BLOCK_RE.sub(private_key_replacement, text)

    def assignment_replacement(match: re.Match[str]) -> str:
        nonlocal redactions
        value = match.group("value").strip().rstrip(",")
        if not _is_sensitive_key(match.group("key")) or not _contains_secret_value(value):
            return match.group(0)
        redactions += 1
        return f"{match.group('prefix')}__REDACTED__{match.group('suffix')}"

    text = _ASSIGNMENT_RE.sub(assignment_replacement, text)

    def inline_assignment_replacement(match: re.Match[str]) -> str:
        nonlocal redactions
        value = (match.group("quoted_value") or match.group("bare_value") or "").strip().rstrip(",")
        if not _is_sensitive_key(match.group("key")) or not _contains_secret_value(value):
            return match.group(0)
        redactions += 1
        quote = match.group("quote") or ""
        return f"{match.group('prefix')}{quote}__REDACTED__{quote}"

    text = _INLINE_ASSIGNMENT_RE.sub(inline_assignment_replacement, text)
    for pattern in _TOKEN_PATTERNS:
        text, count = pattern.subn("__REDACTED_TOKEN__", text)
        redactions += count
    return text, redactions
