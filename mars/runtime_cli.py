from __future__ import annotations

import os
import shutil
from pathlib import Path, PurePosixPath
from typing import Any

from django.conf import settings

from mars.policy import MarsPolicyError


def _command_prefix(value: Any, default: str) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item)]
    raw = str(value or default).strip()
    return [raw] if raw else [default]


def _command_uses_wsl_windows_exe(command: list[str]) -> bool:
    if os.name != "posix" or not command:
        return False
    executable = command[0].replace("\\", "/").lower()
    return executable.startswith("/mnt/") and executable.endswith(".exe")


def _wsl_path_to_windows(path: Path) -> str:
    raw = str(path.resolve(strict=False)).replace("\\", "/")
    if not raw.startswith("/mnt/") or len(raw) < 7:
        return str(path)
    drive = raw[5].upper()
    rest = raw[7:].replace("/", "\\")
    return f"{drive}:\\{rest}"


def cli_path_for_command(command: list[str], path: str | Path) -> str:
    resolved = Path(path).expanduser().resolve(strict=False)
    return _wsl_path_to_windows(resolved) if _command_uses_wsl_windows_exe(command) else str(resolved)


def _command_is_codex(command: list[str]) -> bool:
    if not command:
        return False
    executable = command[0].replace("\\", "/").lower()
    return executable.endswith("/codex") or executable.endswith("/codex.exe") or executable == "codex"


def _codex_home_candidates() -> list[Path]:
    candidates: list[Path] = []
    raw_env_home = os.environ.get("CODEX_HOME")
    if raw_env_home:
        candidates.append(Path(raw_env_home).expanduser())
    candidates.append(Path.home() / ".codex")
    wsl_users_root = Path("/mnt/c/Users")
    if wsl_users_root.exists():
        for user_dir in wsl_users_root.iterdir():
            candidates.append(user_dir / ".codex")
    return candidates


def ensure_mars_codex_home(command: list[str]) -> Path | None:
    if not _command_is_codex(command):
        return None
    configured = Path(getattr(settings, "MARS_CODEX_HOME", Path(settings.MEDIA_ROOT) / "mars_codex_home")).expanduser()
    if _command_uses_wsl_windows_exe(command) and str(configured) == str(Path.home() / ".mars_codex_home"):
        for candidate_home in _codex_home_candidates():
            try:
                if (
                    str(candidate_home).replace("\\", "/").startswith("/mnt/c/Users/")
                    and (candidate_home / "auth.json").exists()
                ):
                    configured = candidate_home.parent / ".mars_codex_home"
                    break
            except OSError:
                continue
    if not configured.is_absolute():
        configured = Path(settings.BASE_DIR) / configured
    home = configured.resolve(strict=False)
    home.mkdir(parents=True, exist_ok=True)

    config_path = home / "config.toml"
    if not config_path.exists():
        config_path.write_text(
            "# Isolated Codex home for MARS. Keep plugins and MCP servers out of this runtime.\n",
            encoding="utf-8",
        )

    auth_target = home / "auth.json"
    if not auth_target.exists():
        for candidate_home in _codex_home_candidates():
            auth_source = candidate_home / "auth.json"
            try:
                if auth_source.exists():
                    shutil.copy2(auth_source, auth_target)
                    break
            except OSError:
                continue
    return home


def subprocess_env_for_cli(command: list[str]) -> dict[str, str]:
    env = os.environ.copy()
    codex_home = ensure_mars_codex_home(command)
    if codex_home is not None:
        if _command_uses_wsl_windows_exe(command):
            env["CODEX_HOME"] = str(codex_home)
            existing_wslenv = env.get("WSLENV", "")
            entries = [item for item in existing_wslenv.split(":") if item]
            if "CODEX_HOME/p" not in entries:
                entries.append("CODEX_HOME/p")
            env["WSLENV"] = ":".join(entries)
        else:
            env["CODEX_HOME"] = str(codex_home)
    return env


def mars_agent_uses_docker() -> bool:
    runtime = str(getattr(settings, "MARS_AGENT_RUNTIME", "host") or "host").strip().lower()
    return runtime in {"docker", "container", "containers"}


def docker_workspace_path() -> str:
    workdir = str(getattr(settings, "MARS_AGENT_DOCKER_WORKDIR", "/workspace") or "/workspace").strip()
    return workdir if workdir.startswith("/") else "/workspace"


def _docker_host_path(path: str | Path) -> str:
    resolved = Path(path).expanduser().resolve(strict=False)
    container_prefix = (
        str(getattr(settings, "MARS_DOCKER_CONTAINER_PATH_PREFIX", "") or "").replace("\\", "/").rstrip("/")
    )
    host_prefix = str(getattr(settings, "MARS_DOCKER_HOST_PATH_PREFIX", "") or "").strip()
    normalized = str(resolved).replace("\\", "/")
    if (
        container_prefix
        and host_prefix
        and (normalized == container_prefix or normalized.startswith(f"{container_prefix}/"))
    ):
        suffix = normalized[len(container_prefix) :].lstrip("/")
        clean_host_prefix = host_prefix.rstrip("\\/")
        if ":" in clean_host_prefix[:4] or "\\" in clean_host_prefix:
            return clean_host_prefix + (("\\" + suffix.replace("/", "\\")) if suffix else "")
        host_base = Path(clean_host_prefix).expanduser()
        return (
            str((host_base / PurePosixPath(suffix)).resolve(strict=False))
            if suffix
            else str(host_base.resolve(strict=False))
        )
    return str(resolved)


def _docker_volume_arg(source: str | Path, target: str, mode: str) -> str:
    safe_mode = "ro" if mode == "ro" else "rw"
    return f"{_docker_host_path(source)}:{target}:{safe_mode}"


def _docker_named_volume_mount(volume_name: str, target: str, readonly: bool = False) -> str:
    clean_name = volume_name.strip()
    if not clean_name or any(char in clean_name for char in " ,"):
        raise MarsPolicyError("Invalid Docker volume name for MARS agent runtime.")
    parts = ["type=volume", f"src={clean_name}", f"dst={target}"]
    if readonly:
        parts.append("readonly")
    return ",".join(parts)


def docker_container_child_path(container_root: str, host_root: str | Path, host_child: str | Path) -> str:
    root = Path(host_root).expanduser().resolve(strict=False)
    child = Path(host_child).expanduser().resolve(strict=False)
    rel = child.relative_to(root)
    return str(PurePosixPath(container_root) / PurePosixPath(rel.as_posix()))


def _docker_env_passthrough() -> list[str]:
    names = [
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_CLOUD_PROJECT",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
    ]
    args: list[str] = []
    for name in names:
        if os.environ.get(name):
            args.extend(["-e", name])
    return args


def build_mars_agent_docker_command(
    *,
    phase: str,
    workspace_root: str | Path,
    workspace_mode: str,
    inner_command: list[str],
    extra_mounts: list[tuple[str | Path, str, str]] | None = None,
    include_codex_home: bool = False,
    include_gemini_home: bool = False,
) -> list[str]:
    workspace = Path(workspace_root).expanduser().resolve(strict=False)
    docker_command = str(getattr(settings, "MARS_AGENT_DOCKER_COMMAND", "docker") or "docker")
    image = str(getattr(settings, "MARS_AGENT_DOCKER_IMAGE", "webterm-mars-agent:latest") or "").strip()
    if not image:
        raise MarsPolicyError("MARS_AGENT_DOCKER_IMAGE is not configured.")

    command = [
        docker_command,
        "run",
        "--rm",
        "--interactive",
        "--workdir",
        docker_workspace_path(),
        "--network",
        str(getattr(settings, "MARS_AGENT_DOCKER_NETWORK", "bridge") or "bridge"),
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=512m",
        "--label",
        f"webtrerm.mars.phase={phase}",
        "-v",
        _docker_volume_arg(workspace, docker_workspace_path(), workspace_mode),
    ]

    cpus = str(getattr(settings, "MARS_AGENT_DOCKER_CPUS", "") or "").strip()
    memory = str(getattr(settings, "MARS_AGENT_DOCKER_MEMORY", "") or "").strip()
    pids_limit = int(getattr(settings, "MARS_AGENT_DOCKER_PIDS_LIMIT", 0) or 0)
    if cpus:
        command.extend(["--cpus", cpus])
    if memory:
        command.extend(["--memory", memory])
    if pids_limit > 0:
        command.extend(["--pids-limit", str(pids_limit)])

    for source, target, mode in extra_mounts or []:
        command.extend(["-v", _docker_volume_arg(source, target, mode)])

    if include_codex_home:
        command.extend(["-e", "CODEX_HOME=/codex-home"])
        codex_home_volume = str(getattr(settings, "MARS_AGENT_DOCKER_CODEX_HOME_VOLUME", "") or "").strip()
        if codex_home_volume:
            command.extend(["--mount", _docker_named_volume_mount(codex_home_volume, "/codex-home")])
            ensure_mars_codex_home(["codex"])
        else:
            codex_home = ensure_mars_codex_home(["codex"])
            if codex_home is not None:
                command.extend(["-v", _docker_volume_arg(codex_home, "/codex-home", "rw")])

    if include_gemini_home:
        gemini_home_volume = str(getattr(settings, "MARS_AGENT_DOCKER_GEMINI_HOME_VOLUME", "") or "").strip()
        gemini_home = (
            Path(getattr(settings, "MARS_GEMINI_HOME", Path.home() / ".gemini")).expanduser().resolve(strict=False)
        )
        if gemini_home_volume:
            command.extend(
                ["--mount", _docker_named_volume_mount(gemini_home_volume, "/home/node/.gemini", readonly=True)]
            )
        elif gemini_home.exists():
            command.extend(["-v", _docker_volume_arg(gemini_home, "/home/node/.gemini", "ro")])

    command.extend(_docker_env_passthrough())
    command.append(image)
    command.extend(inner_command)
    return command
