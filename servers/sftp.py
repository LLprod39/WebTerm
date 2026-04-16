from __future__ import annotations

import contextlib
import posixpath
import re
import stat as stat_module
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from tempfile import SpooledTemporaryFile
from typing import Any

import asyncssh
from asyncssh import sftp as asyncssh_sftp

from servers.models import Server
from servers.ssh_host_keys import build_server_connect_kwargs, ensure_server_known_hosts

TEXT_FILE_MAX_BYTES = 256 * 1024
OWNER_GROUP_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


def _normalize_path_value(value: bytes | str | asyncssh_sftp.SFTPName) -> str:
    if isinstance(value, asyncssh_sftp.SFTPName):
        value = value.filename
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def normalize_remote_name(name: str) -> str:
    value = str(name or "").strip()
    if not value or value in {".", ".."}:
        raise ValueError("Некорректное имя файла или папки")
    if "/" in value or "\\" in value:
        raise ValueError("Имя не должно содержать разделители пути")
    return value


def join_remote_path(parent_path: str, name: str) -> str:
    clean_name = normalize_remote_name(name)
    if parent_path == "/":
        return f"/{clean_name}"
    return posixpath.join(parent_path or ".", clean_name)


def _entry_kind(attrs: asyncssh.SFTPAttrs) -> str:
    entry_type = getattr(attrs, "type", asyncssh_sftp.FILEXFER_TYPE_UNKNOWN)
    permissions = getattr(attrs, "permissions", None)

    if entry_type == asyncssh_sftp.FILEXFER_TYPE_DIRECTORY:
        return "dir"
    if entry_type == asyncssh_sftp.FILEXFER_TYPE_SYMLINK:
        return "symlink"
    if entry_type == asyncssh_sftp.FILEXFER_TYPE_REGULAR:
        return "file"
    if permissions is not None and stat_module.S_ISDIR(permissions):
        return "dir"
    if permissions is not None and stat_module.S_ISLNK(permissions):
        return "symlink"
    return "file"


def _serialize_entry(path: str, name: str, attrs: asyncssh.SFTPAttrs) -> dict[str, Any]:
    kind = _entry_kind(attrs)
    permissions = getattr(attrs, "permissions", None)
    return {
        "name": name,
        "path": path,
        "kind": kind,
        "is_dir": kind == "dir",
        "is_symlink": kind == "symlink",
        "size": int(getattr(attrs, "size", 0) or 0),
        "permissions": stat_module.filemode(permissions) if isinstance(permissions, int) else "",
        "permissions_octal": format(permissions & 0o7777, "04o") if isinstance(permissions, int) else "",
        "modified_at": int(getattr(attrs, "mtime", 0) or 0),
    }


@asynccontextmanager
async def open_server_sftp(server: Server, *, secret: str = "") -> AsyncIterator[asyncssh_sftp.SFTPClient]:
    known_hosts = await ensure_server_known_hosts(server)
    connect_kwargs = build_server_connect_kwargs(server, secret=secret, known_hosts=known_hosts)
    async with asyncssh.connect(**connect_kwargs) as conn, conn.start_sftp_client() as sftp:
        yield sftp


async def resolve_remote_path(sftp: asyncssh_sftp.SFTPClient, path: str | None) -> str:
    target = path or "."
    resolved = await sftp.realpath(target)
    return _normalize_path_value(resolved)


async def resolve_remote_file_path(sftp: asyncssh_sftp.SFTPClient, path: str | None) -> str:
    target = str(path or "").strip()
    if not target:
        raise ValueError("Не указан путь к файлу")

    normalized_target = target.replace("\\", "/")
    filename = posixpath.basename(normalized_target.rstrip("/"))
    if not filename or filename in {".", ".."}:
        raise ValueError("Некорректный путь к файлу")

    parent_hint = posixpath.dirname(normalized_target) or "."
    parent_path = await resolve_remote_path(sftp, parent_hint)
    parent_attrs = await sftp.stat(parent_path)
    if _entry_kind(parent_attrs) != "dir":
        raise NotADirectoryError(parent_path)

    return join_remote_path(parent_path, filename)


def normalize_permission_mode(mode: str | int) -> int:
    if isinstance(mode, int):
        return mode & 0o7777

    raw_mode = str(mode or "").strip()
    if not re.fullmatch(r"[0-7]{3,4}", raw_mode):
        raise ValueError("Укажите права в octal формате, например 644 или 0755")
    return int(raw_mode, 8)


def normalize_owner_group(value: str | None, *, label: str) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    if not OWNER_GROUP_NAME_PATTERN.fullmatch(normalized):
        raise ValueError(f"Некорректное значение поля {label}")
    return normalized


async def get_directory_listing(server: Server, *, secret: str = "", path: str | None = None) -> dict[str, Any]:
    async with open_server_sftp(server, secret=secret) as sftp:
        current_path = await resolve_remote_path(sftp, path)
        attrs = await sftp.stat(current_path)
        if _entry_kind(attrs) != "dir":
            raise NotADirectoryError(current_path)

        entries: list[dict[str, Any]] = []
        async for entry in sftp.scandir(current_path):
            name = _normalize_path_value(entry.filename)
            if not name or name in {".", ".."}:
                continue
            entry_path = join_remote_path(current_path, name)
            entries.append(_serialize_entry(entry_path, name, entry.attrs))

        entries.sort(key=lambda item: (not item["is_dir"], item["name"].lower()))
        home_path = await resolve_remote_path(sftp, ".")
        parent_path = None
        if current_path != "/":
            parent_candidate = posixpath.dirname(current_path.rstrip("/")) or "/"
            parent_path = parent_candidate if parent_candidate != current_path else None

        return {
            "path": current_path,
            "home_path": home_path,
            "parent_path": parent_path,
            "entries": entries,
        }


async def create_directory(server: Server, *, secret: str = "", parent_path: str | None, name: str) -> dict[str, Any]:
    async with open_server_sftp(server, secret=secret) as sftp:
        base_path = await resolve_remote_path(sftp, parent_path)
        target_path = join_remote_path(base_path, name)
        await sftp.mkdir(target_path)
        attrs = await sftp.stat(target_path)
        return {
            "path": base_path,
            "entry": _serialize_entry(target_path, normalize_remote_name(name), attrs),
        }


async def rename_path(server: Server, *, secret: str = "", path: str, new_name: str) -> dict[str, Any]:
    async with open_server_sftp(server, secret=secret) as sftp:
        source_path = await resolve_remote_path(sftp, path)
        parent_path = posixpath.dirname(source_path.rstrip("/")) or "/"
        target_name = normalize_remote_name(new_name)
        target_path = join_remote_path(parent_path, target_name)
        await sftp.rename(source_path, target_path)
        attrs = await sftp.stat(target_path)
        return {
            "path": parent_path,
            "entry": _serialize_entry(target_path, target_name, attrs),
        }


async def _remove_tree(sftp: asyncssh_sftp.SFTPClient, target_path: str) -> None:
    attrs = await sftp.lstat(target_path)
    if _entry_kind(attrs) != "dir":
        await sftp.remove(target_path)
        return

    async for entry in sftp.scandir(target_path):
        name = _normalize_path_value(entry.filename)
        if not name or name in {".", ".."}:
            continue
        await _remove_tree(sftp, join_remote_path(target_path, name))

    await sftp.rmdir(target_path)


async def _walk_tree_paths(sftp: asyncssh_sftp.SFTPClient, target_path: str) -> list[str]:
    attrs = await sftp.lstat(target_path)
    paths = [target_path]
    if _entry_kind(attrs) != "dir":
        return paths

    async for entry in sftp.scandir(target_path):
        name = _normalize_path_value(entry.filename)
        if not name or name in {".", ".."}:
            continue
        child_path = join_remote_path(target_path, name)
        paths.extend(await _walk_tree_paths(sftp, child_path))
    return paths


async def delete_path(server: Server, *, secret: str = "", path: str, recursive: bool = False) -> dict[str, Any]:
    async with open_server_sftp(server, secret=secret) as sftp:
        target_path = await resolve_remote_path(sftp, path)
        parent_path = posixpath.dirname(target_path.rstrip("/")) or "/"
        attrs = await sftp.lstat(target_path)
        if _entry_kind(attrs) == "dir":
            if not recursive:
                raise IsADirectoryError(target_path)
            await _remove_tree(sftp, target_path)
        else:
            await sftp.remove(target_path)

        return {
            "path": parent_path,
            "deleted_path": target_path,
        }


async def upload_local_file(
    server: Server,
    *,
    secret: str = "",
    remote_dir: str | None,
    local_path: str,
    remote_name: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    async with open_server_sftp(server, secret=secret) as sftp:
        target_dir = await resolve_remote_path(sftp, remote_dir)
        target_name = normalize_remote_name(remote_name)
        remote_path = join_remote_path(target_dir, target_name)
        if not overwrite and await sftp.exists(remote_path):
            raise FileExistsError(remote_path)

        await sftp.put(local_path, remote_path)
        attrs = await sftp.stat(remote_path)
        return {
            "path": target_dir,
            "entry": _serialize_entry(remote_path, target_name, attrs),
        }


async def download_file(
    server: Server,
    *,
    secret: str = "",
    path: str,
    spool_max_size: int = 8 * 1024 * 1024,
) -> dict[str, Any]:
    async with open_server_sftp(server, secret=secret) as sftp:
        target_path = await resolve_remote_path(sftp, path)
        attrs = await sftp.stat(target_path)
        if _entry_kind(attrs) == "dir":
            raise IsADirectoryError(target_path)

        local_file = SpooledTemporaryFile(max_size=spool_max_size, mode="w+b")
        async with sftp.open(target_path, "rb", encoding=None) as remote_file:
            while True:
                chunk = await remote_file.read(256 * 1024)
                if not chunk:
                    break
                local_file.write(chunk)

        local_file.seek(0)
        return {
            "path": target_path,
            "filename": posixpath.basename(target_path),
            "size": int(getattr(attrs, "size", 0) or 0),
            "file_obj": local_file,
        }


async def read_text_file(
    server: Server,
    *,
    secret: str = "",
    path: str,
    max_bytes: int = TEXT_FILE_MAX_BYTES,
) -> dict[str, Any]:
    async with open_server_sftp(server, secret=secret) as sftp:
        target_path = await resolve_remote_path(sftp, path)
        attrs = await sftp.stat(target_path)
        if _entry_kind(attrs) == "dir":
            raise IsADirectoryError(target_path)

        file_size = int(getattr(attrs, "size", 0) or 0)
        if file_size > max_bytes:
            raise ValueError(f"Файл слишком большой для редактора (>{max_bytes} bytes)")

        async with sftp.open(target_path, "rb", encoding=None) as remote_file:
            raw_content = await remote_file.read(max_bytes + 1)

        if len(raw_content) > max_bytes:
            raise ValueError(f"Файл слишком большой для редактора (>{max_bytes} bytes)")

        try:
            content = raw_content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Файл не является UTF-8 текстом") from exc

        return {
            "path": target_path,
            "filename": posixpath.basename(target_path),
            "size": file_size,
            "encoding": "utf-8",
            "content": content,
        }


async def write_text_file(
    server: Server,
    *,
    secret: str = "",
    path: str,
    content: str,
    max_bytes: int = TEXT_FILE_MAX_BYTES,
) -> dict[str, Any]:
    async with open_server_sftp(server, secret=secret) as sftp:
        target_path = await resolve_remote_file_path(sftp, path)
        attrs = None
        if await sftp.exists(target_path):
            attrs = await sftp.stat(target_path)
            if _entry_kind(attrs) == "dir":
                raise IsADirectoryError(target_path)

        payload = str(content or "").encode("utf-8")
        if len(payload) > max_bytes:
            raise ValueError(f"Файл слишком большой для сохранения через редактор (>{max_bytes} bytes)")

        parent_path = posixpath.dirname(target_path.rstrip("/")) or "/"
        filename = posixpath.basename(target_path)
        temp_path = join_remote_path(parent_path, f".{filename}.tmp-{uuid.uuid4().hex}")

        try:
            async with sftp.open(temp_path, "wb", encoding=None) as remote_file:
                await remote_file.write(payload)

            permissions = getattr(attrs, "permissions", None)
            if isinstance(permissions, int):
                await sftp.chmod(temp_path, permissions & 0o7777)

            if await sftp.exists(target_path):
                await sftp.remove(target_path)
            await sftp.rename(temp_path, target_path)
        except Exception:
            with contextlib.suppress(Exception):
                if await sftp.exists(temp_path):
                    await sftp.remove(temp_path)
            raise

        updated_attrs = await sftp.stat(target_path)
        return {
            "path": target_path,
            "filename": posixpath.basename(target_path),
            "size": int(getattr(updated_attrs, "size", 0) or 0),
            "encoding": "utf-8",
            "content": str(content or ""),
        }


async def change_permissions(
    server: Server,
    *,
    secret: str = "",
    path: str,
    mode: str | int,
) -> dict[str, Any]:
    normalized_mode = normalize_permission_mode(mode)
    async with open_server_sftp(server, secret=secret) as sftp:
        target_path = await resolve_remote_path(sftp, path)
        await sftp.chmod(target_path, normalized_mode)
        attrs = await sftp.stat(target_path)
        return {
            "path": posixpath.dirname(target_path.rstrip("/")) or "/",
            "entry": _serialize_entry(target_path, posixpath.basename(target_path), attrs),
        }


async def change_owner(
    server: Server,
    *,
    secret: str = "",
    path: str,
    owner: str | None = None,
    group: str | None = None,
    recursive: bool = False,
) -> dict[str, Any]:
    normalized_owner = normalize_owner_group(owner, label="owner")
    normalized_group = normalize_owner_group(group, label="group")
    if not normalized_owner and not normalized_group:
        raise ValueError("Укажите owner, group или оба значения")

    async with open_server_sftp(server, secret=secret) as sftp:
        target_path = await resolve_remote_path(sftp, path)
        targets = await _walk_tree_paths(sftp, target_path) if recursive else [target_path]
        for item_path in targets:
            await sftp.chown(
                item_path,
                owner=normalized_owner,
                group=normalized_group,
                follow_symlinks=False,
            )
        attrs = await sftp.stat(target_path)
        return {
            "path": posixpath.dirname(target_path.rstrip("/")) or "/",
            "entry": _serialize_entry(target_path, posixpath.basename(target_path), attrs),
        }
