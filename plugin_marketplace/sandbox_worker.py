from __future__ import annotations

import argparse
import importlib.util
import json
import socket
import sys
import tempfile
import traceback
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


def _load_archive_path_controls():
    module_path = Path(__file__).with_name("archive_paths.py")
    spec = importlib.util.spec_from_file_location("_webtrerm_plugin_archive_paths", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("plugin archive path controls are unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_ARCHIVE_PATHS = _load_archive_path_controls()


def _safe_member(name: str) -> bool:
    return _ARCHIVE_PATHS.is_safe_archive_member(name)


def _parse_executor_ref(executor_ref: str) -> tuple[str, str]:
    if not executor_ref.startswith("sandbox:"):
        raise ValueError("executor_ref must start with sandbox:.")
    target = executor_ref.removeprefix("sandbox:")
    path_part, _, function_name = target.partition(":")
    function_name = function_name or "handle"
    path = PurePosixPath(path_part)
    if not _safe_member(path_part) or not str(path).startswith("backend/") or path.suffix != ".py":
        raise ValueError("sandbox executor must reference a backend/*.py file.")
    if not function_name.isidentifier():
        raise ValueError("sandbox executor function name is invalid.")
    return str(path), function_name


def _extract_package(package_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(package_path) as archive:
        members = []
        for member in archive.infolist():
            if member.is_dir():
                continue
            if not _safe_member(member.filename):
                raise ValueError(f"unsafe package path: {member.filename}")
            _ARCHIVE_PATHS.archive_member_target(destination, member.filename)
            members.append(member)
        for member in members:
            target = _ARCHIVE_PATHS.archive_member_target(destination, member.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(member))


def _load_manifest(root: Path) -> dict[str, Any]:
    for path in sorted(root.rglob("webtrerm.plugin.json")):
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _normalize_host(value: Any) -> str:
    return str(value or "").strip().strip(".").lower()


def _port_values(values: Any) -> set[int]:
    if not isinstance(values, list):
        return set()
    ports: set[int] = set()
    for item in values:
        try:
            port = int(item)
        except (TypeError, ValueError):
            continue
        if 0 < port <= 65535:
            ports.add(port)
    return ports


def _declared_egress(manifest: dict[str, Any]) -> dict[str, set[int]]:
    allowed: dict[str, set[int]] = {}
    egress = manifest.get("egress") if isinstance(manifest.get("egress"), list) else []
    for item in egress:
        if not isinstance(item, dict):
            continue
        hosts = []
        host = _normalize_host(item.get("host"))
        if host:
            hosts.append(host)
        for field in ("hosts", "hostnames"):
            values = item.get(field) if isinstance(item.get(field), list) else []
            hosts.extend(_normalize_host(value) for value in values if _normalize_host(value))
        ports = _port_values(item.get("ports"))
        for declared_host in hosts:
            allowed.setdefault(declared_host, set()).update(ports)
    return allowed


def _address_host_port(address: Any) -> tuple[str, int | None]:
    if isinstance(address, tuple) and len(address) >= 2:
        try:
            port = int(address[1])
        except (TypeError, ValueError):
            port = None
        return _normalize_host(address[0]), port
    return "", None


def _install_egress_guard(manifest: dict[str, Any]) -> None:
    allowed = _declared_egress(manifest)
    original_create_connection = socket.create_connection
    original_socket_connect = socket.socket.connect

    def check_address(address: Any) -> None:
        host, port = _address_host_port(address)
        if not host:
            raise PermissionError("Sandbox network egress is denied for non-TCP sockets.")
        allowed_ports = allowed.get(host)
        if allowed_ports is None:
            raise PermissionError(f"Sandbox network egress to {host} is not declared.")
        if allowed_ports and port not in allowed_ports:
            raise PermissionError(f"Sandbox network egress to {host}:{port} is not declared.")

    def guarded_create_connection(address, *args, **kwargs):
        check_address(address)
        return original_create_connection(address, *args, **kwargs)

    def guarded_socket_connect(self, address):
        check_address(address)
        return original_socket_connect(self, address)

    socket.create_connection = guarded_create_connection
    socket.socket.connect = guarded_socket_connect


def _load_handler(root: Path, relative_path: str, function_name: str):
    module_path = root / relative_path
    if not module_path.is_file():
        raise ValueError(f"sandbox executor file not found: {relative_path}")
    spec = importlib.util.spec_from_file_location("webtrerm_plugin_sandbox", module_path)
    if spec is None or spec.loader is None:
        raise ValueError("sandbox executor module could not be loaded.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    handler = getattr(module, function_name, None)
    if not callable(handler):
        raise ValueError(f"sandbox executor function not found: {function_name}")
    return handler


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return {"repr": repr(value)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True)
    parser.add_argument("--executor-ref", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--project-root", default="")
    parser.add_argument("--smoke-only", action="store_true")
    args = parser.parse_args()

    project_root = str(Path(args.project_root).resolve()) if args.project_root else ""
    if project_root:
        sys.path = [item for item in sys.path if project_root not in str(Path(item or ".").resolve())]

    try:
        relative_path, function_name = _parse_executor_ref(args.executor_ref)
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="webtrerm-plugin-sandbox-") as temp_dir:
            root = Path(temp_dir)
            _extract_package(Path(args.package), root)
            _install_egress_guard(_load_manifest(root))
            handler = _load_handler(root, relative_path, function_name)
            if args.smoke_only:
                result = {"executor_ref": args.executor_ref, "loaded": callable(handler)}
            else:
                result = handler(payload)
        output = {"success": True, "result": _json_safe(result)}
    except Exception as exc:  # noqa: BLE001 - worker must serialize all failures.
        output = {
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=5),
        }
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
