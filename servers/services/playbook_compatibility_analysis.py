"""Static compatibility analysis and semantic guards for imported Ansible playbooks."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from servers.services.playbooks.controller_policy import analyze_playbook_controller_policy

_TASK_META_KEYS = {
    "name",
    "when",
    "register",
    "become",
    "become_user",
    "tags",
    "notify",
    "ignore_errors",
    "changed_when",
    "failed_when",
    "loop",
    "loop_control",
    "with_items",
    "vars",
    "environment",
    "no_log",
    "delegate_to",
    "run_once",
    "block",
    "rescue",
    "always",
    "args",
    "throttle",
    "retries",
    "delay",
    "until",
    "check_mode",
    "diff",
    "listen",
    "collections",
}
_PROTECTED_TASK_META = tuple(sorted(_TASK_META_KEYS - {"name"}))
_PLAY_CONTROL_KEYS = (
    "any_errors_fatal",
    "become",
    "become_user",
    "force_handlers",
    "gather_facts",
    "max_fail_percentage",
    "order",
    "serial",
    "strategy",
)
_PLAY_CONTEXT_KEYS = (
    "collections",
    "environment",
    "module_defaults",
    "no_log",
    "vars",
    "vars_files",
)
_HOST_TOKEN_RE = re.compile(r"[A-Za-z0-9_.-]+")
_JINJA_VAR_RE = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_.]*)")
_SENSITIVE_KEY_RE = re.compile(r"(?:pass(?:word)?|secret|token|api[_-]?key|private[_-]?key|vault)", re.I)
_LOCAL_ASSET_MODULES = {"template", "script", "include_tasks", "import_tasks"}
_BUILTIN_VARS = {
    "ansible_facts",
    "ansible_host",
    "ansible_os_family",
    "ansible_user",
    "group_names",
    "groups",
    "hostvars",
    "inventory_hostname",
    "inventory_hostname_short",
    "item",
    "lookup",
    "omit",
    "playbook_dir",
    "query",
    "role_path",
}
COMPATIBILITY_ANALYZER_VERSION = 3


def _load_yaml(source_yaml: str) -> list[dict[str, Any]]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ValueError("PyYAML is required") from exc
    try:
        document = yaml.safe_load(source_yaml)
    except Exception as exc:
        raise ValueError(f"Invalid YAML: {exc}") from exc
    plays = document if isinstance(document, list) else [document]
    if not plays or not all(isinstance(play, dict) for play in plays):
        raise ValueError("Ansible playbook must contain a play or a list of plays")
    return plays


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _canonical(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def _module_name(task: dict[str, Any]) -> str:
    action = task.get("action")
    if isinstance(action, str) and action.strip():
        return action.split()[0]
    for key in task:
        if key not in _TASK_META_KEYS:
            if key.startswith("ansible.builtin.") or key.startswith("ansible.legacy."):
                return key.rsplit(".", 1)[-1]
            return key
    return ""


def _module_args(task: dict[str, Any], module: str) -> Any:
    if "action" in task and isinstance(task.get("action"), str):
        return str(task["action"]).partition(" ")[2]
    for key, value in task.items():
        normalized = key.rsplit(".", 1)[-1] if key.startswith(("ansible.builtin.", "ansible.legacy.")) else key
        if normalized == module or key == module:
            return _canonical(value)
    return None


def _task_manifest(task: dict[str, Any]) -> dict[str, Any]:
    module = _module_name(task)
    item: dict[str, Any] = {
        "module": module,
        "args": _module_args(task, module),
        "controls": {key: _canonical(task[key]) for key in _PROTECTED_TASK_META if key in task},
    }
    for section in ("block", "rescue", "always"):
        nested = task.get(section)
        if isinstance(nested, list):
            item[section] = [_task_manifest(child) for child in nested if isinstance(child, dict)]
    return item


def build_semantic_manifest(source_yaml: str) -> dict[str, Any]:
    """Build the behavior-protected portion of a playbook.

    Host selectors, human-readable names, play vars and environment are intentionally
    omitted: those form the compatibility layer. Tasks, roles, ordering and execution
    controls are protected.
    """
    plays = _load_yaml(source_yaml)
    manifest_plays: list[dict[str, Any]] = []
    for play in plays:
        protected: dict[str, Any] = {
            "controls": {key: _canonical(play[key]) for key in _PLAY_CONTROL_KEYS if key in play},
            "context": {key: _canonical(play[key]) for key in _PLAY_CONTEXT_KEYS if key in play},
            "roles": _canonical(play.get("roles") or []),
        }
        for section in ("pre_tasks", "tasks", "post_tasks", "handlers"):
            raw_tasks = play.get(section)
            if isinstance(raw_tasks, list):
                protected[section] = [_task_manifest(task) for task in raw_tasks if isinstance(task, dict)]
            else:
                protected[section] = []
        manifest_plays.append(protected)
    payload = {"plays": manifest_plays}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["sha256"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return payload


def compare_semantics(original_yaml: str, adapted_yaml: str) -> dict[str, Any]:
    try:
        original = build_semantic_manifest(original_yaml)
        adapted = build_semantic_manifest(adapted_yaml)
    except ValueError as exc:
        return {"passed": False, "violations": [str(exc)], "original_hash": "", "adapted_hash": ""}
    passed = original["sha256"] == adapted["sha256"]
    return {
        "passed": passed,
        "violations": [] if passed else ["Protected task, role, order, condition, or execution control changed"],
        "original_hash": original["sha256"],
        "adapted_hash": adapted["sha256"],
    }


def _host_tokens(value: Any) -> tuple[list[str], str]:
    pattern = ":".join(str(item) for item in value) if isinstance(value, list) else str(value or "")
    if "{{" in pattern or "{%" in pattern:
        return [], pattern
    tokens: list[str] = []
    for match in _HOST_TOKEN_RE.findall(pattern):
        if match.lower() in {"all", "localhost"} or match.isdigit():
            continue
        if match not in tokens:
            tokens.append(match)
    return tokens, pattern


def _walk_tasks(play: dict[str, Any]):
    for section in ("pre_tasks", "tasks", "post_tasks", "handlers"):
        tasks = play.get(section)
        if not isinstance(tasks, list):
            continue
        for index, task in enumerate(tasks):
            if not isinstance(task, dict):
                continue
            yield f"{section}[{index}]", task
            for nested_name in ("block", "rescue", "always"):
                nested = task.get(nested_name)
                if isinstance(nested, list):
                    for nested_index, child in enumerate(nested):
                        if isinstance(child, dict):
                            yield f"{section}[{index}].{nested_name}[{nested_index}]", child


def _issue(code: str, severity: str, message: str, path: str = "") -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message, "path": path}


def _literal_secret_paths(value: Any, path: str = "playbook") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if _SENSITIVE_KEY_RE.search(str(key)) and isinstance(child, (str, int, float)):
                text = str(child)
                if text and "{{" not in text:
                    found.append(child_path)
            found.extend(_literal_secret_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_literal_secret_paths(child, f"{path}[{index}]"))
    return found


def analyze_playbook_compatibility(
    source_yaml: str,
    *,
    bindings: dict[str, Any] | None = None,
    target_servers: list[Any] | None = None,
) -> dict[str, Any]:
    """Return a deterministic compatibility report without executing anything."""
    bindings = bindings if isinstance(bindings, dict) else {}
    target_servers = target_servers or []
    issues: list[dict[str, str]] = []
    try:
        plays = _load_yaml(source_yaml)
        manifest = build_semantic_manifest(source_yaml)
    except ValueError as exc:
        return {
            "analyzer_version": COMPATIBILITY_ANALYZER_VERSION,
            "status": "blocked",
            "ready": False,
            "host_selectors": [],
            "host_patterns": [],
            "missing_bindings": [],
            "required_variables": [],
            "dependencies": {"roles": [], "collections": [], "assets": []},
            "issues": [_issue("invalid_yaml", "error", str(exc))],
            "semantic_hash": "",
        }

    selectors: list[str] = []
    host_patterns: list[str] = []
    roles: set[str] = set()
    collections: set[str] = set()
    assets: set[str] = set()
    used_vars: set[str] = set(_JINJA_VAR_RE.findall(source_yaml))
    declared_vars: set[str] = set()
    module_names: set[str] = set()
    for secret_path in _literal_secret_paths(plays):
        issues.append(
            _issue(
                "literal_secret",
                "error",
                "Literal secret-like value must be replaced before AI adaptation",
                secret_path,
            )
        )
    issues.extend(analyze_playbook_controller_policy(plays))

    for play in plays:
        play_selectors, pattern = _host_tokens(play.get("hosts"))
        if pattern:
            host_patterns.append(pattern)
        if "{{" in pattern or "{%" in pattern:
            issues.append(
                _issue(
                    "dynamic_host_pattern",
                    "warning",
                    "Templated hosts pattern requires a runtime variable instead of inventory binding",
                    "hosts",
                )
            )
        for selector in play_selectors:
            if selector not in selectors:
                selectors.append(selector)
        play_vars = play.get("vars")
        if isinstance(play_vars, dict):
            declared_vars.update(str(key) for key in play_vars)
        for value in play.get("roles") or []:
            role_name = value.get("role") if isinstance(value, dict) else value
            if role_name:
                roles.add(str(role_name))
        for collection in play.get("collections") or []:
            collections.add(str(collection))
        for vars_file in play.get("vars_files") or []:
            assets.add(str(vars_file))

        for path, task in _walk_tasks(play):
            registered = task.get("register")
            if isinstance(registered, str) and registered:
                declared_vars.add(registered)
            loop_control = task.get("loop_control")
            if isinstance(loop_control, dict) and isinstance(loop_control.get("loop_var"), str):
                declared_vars.add(str(loop_control["loop_var"]))
            module = _module_name(task)
            module_names.add(module)
            if module.count(".") >= 2 and not module.startswith(("ansible.builtin.", "ansible.legacy.")):
                collections.add(".".join(module.split(".")[:2]))
            short_module = module.rsplit(".", 1)[-1]
            payload = _module_args(task, short_module)
            if short_module in {"include_role", "import_role"} and isinstance(payload, dict) and payload.get("name"):
                roles.add(str(payload["name"]))
            if short_module in _LOCAL_ASSET_MODULES:
                if isinstance(payload, dict):
                    asset = payload.get("src") or payload.get("file") or payload.get("name")
                else:
                    asset = payload
                if asset:
                    assets.add(str(asset))
            if (
                short_module == "copy"
                and isinstance(payload, dict)
                and payload.get("src")
                and not payload.get("remote_src")
            ):
                assets.add(str(payload["src"]))
            if short_module == "add_host":
                issues.append(_issue("dynamic_inventory", "warning", "Playbook changes inventory at runtime", path))
            if task.get("check_mode") is False:
                issues.append(_issue("check_mode_disabled", "warning", "Task explicitly bypasses check mode", path))
    for role in sorted(roles):
        issues.append(
            _issue("missing_role_bundle", "error", f"Role '{role}' requires an uploaded project bundle", "roles")
        )
    for asset in sorted(assets):
        issues.append(
            _issue("missing_project_asset", "error", f"Local Ansible asset is not included: {asset}", "assets")
        )

    missing_bindings = [
        selector
        for selector in selectors
        if not isinstance(bindings.get(selector), dict)
        or not ((bindings[selector].get("server_ids") or []) or (bindings[selector].get("group_ids") or []))
    ]
    for selector in missing_bindings:
        issues.append(
            _issue("unbound_host_selector", "warning", f"Map '{selector}' to WebTerm servers or groups", "hosts")
        )

    required_vars = sorted(name for name in used_vars if name.split(".", 1)[0] not in declared_vars | _BUILTIN_VARS)
    if required_vars:
        issues.append(
            _issue("required_variables", "warning", "Runtime values required: " + ", ".join(required_vars[:12]), "vars")
        )

    os_kinds = {str(getattr(server, "detected_os", "") or "").lower() for server in target_servers}
    if "apt" in {name.rsplit(".", 1)[-1] for name in module_names} and any(
        kind and not any(part in kind for part in ("debian", "ubuntu")) for kind in os_kinds
    ):
        issues.append(
            _issue("target_os_mismatch", "warning", "apt tasks target at least one non-Debian server", "targets")
        )
    if {"yum", "dnf"} & {name.rsplit(".", 1)[-1] for name in module_names} and any(
        any(part in kind for part in ("debian", "ubuntu")) for kind in os_kinds
    ):
        issues.append(
            _issue("target_os_mismatch", "warning", "yum/dnf tasks target at least one Debian server", "targets")
        )

    errors = [item for item in issues if item["severity"] == "error"]
    adaptation_codes = {"required_variables", "target_os_mismatch", "dynamic_inventory", "dynamic_host_pattern"}
    if errors:
        status = "blocked"
    elif missing_bindings:
        status = "needs_binding"
    elif any(item["code"] in adaptation_codes for item in issues):
        status = "needs_adaptation"
    else:
        status = "ready"
    return {
        "analyzer_version": COMPATIBILITY_ANALYZER_VERSION,
        "status": status,
        "ready": not errors and not missing_bindings,
        "host_selectors": selectors,
        "host_patterns": host_patterns,
        "missing_bindings": missing_bindings,
        "required_variables": required_vars,
        "dependencies": {
            "roles": sorted(roles),
            "collections": sorted(collections),
            "assets": sorted(assets),
        },
        "issues": issues,
        "semantic_hash": manifest["sha256"],
        "targets_count": len(target_servers),
    }


def contains_literal_secrets(report: dict[str, Any]) -> bool:
    return any(item.get("code") == "literal_secret" for item in report.get("issues") or [])
