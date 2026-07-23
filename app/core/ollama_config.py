from __future__ import annotations

import os
import socket
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

OLLAMA_CLOUD_MODEL_SUFFIX = " (cloud)"
OLLAMA_RUNTIME_MODES = {"auto", "local", "cloud"}
OLLAMA_THINK_MODES = {"", "off", "on", "low", "medium", "high"}


def normalize_ollama_base_url(raw: str | None = None) -> str:
    value = ((raw or "").strip() or (os.getenv("OLLAMA_BASE_URL") or "").strip() or "http://127.0.0.1:11434").rstrip(
        "/"
    )
    if "://" not in value:
        value = f"http://{value}"
    return value.rstrip("/")


def normalize_ollama_cloud_base_url(raw: str | None = None) -> str:
    value = ((raw or "").strip() or (os.getenv("OLLAMA_CLOUD_BASE_URL") or "").strip() or "https://ollama.com").rstrip(
        "/"
    )
    if "://" not in value:
        value = f"https://{value}"
    return value.rstrip("/")


def normalize_ollama_runtime_mode(raw: str | None = None) -> str:
    value = (raw or "").strip().lower()
    if value in OLLAMA_RUNTIME_MODES:
        return value
    return "auto"


def normalize_ollama_think_mode(raw: str | None = None) -> str:
    value = (raw or "").strip().lower()
    if value in OLLAMA_THINK_MODES:
        return value
    return ""


def encode_ollama_cloud_model(model_id: str) -> str:
    model_id = (model_id or "").strip()
    if not model_id:
        return ""
    if model_id.endswith(OLLAMA_CLOUD_MODEL_SUFFIX):
        return model_id
    return f"{model_id}{OLLAMA_CLOUD_MODEL_SUFFIX}"


def is_ollama_cloud_model(model_id: str | None) -> bool:
    return (model_id or "").strip().endswith(OLLAMA_CLOUD_MODEL_SUFFIX)


def decode_ollama_cloud_model(model_id: str | None) -> str:
    value = (model_id or "").strip()
    if value.endswith(OLLAMA_CLOUD_MODEL_SUFFIX):
        return value[: -len(OLLAMA_CLOUD_MODEL_SUFFIX)].rstrip()
    return value


def is_wsl_runtime() -> bool:
    if os.getenv("WSL_DISTRO_NAME") or os.getenv("WSL_INTEROP"):
        return True
    for proc_file in ("/proc/sys/kernel/osrelease", "/proc/version"):
        try:
            if "microsoft" in Path(proc_file).read_text(encoding="utf-8", errors="ignore").lower():
                return True
        except OSError:
            continue
    return False


def replace_ollama_host(base_url: str, host: str) -> str:
    parsed = urlsplit(base_url)
    scheme = parsed.scheme or "http"
    port = parsed.port or 11434
    auth = ""
    if parsed.username:
        auth = parsed.username
        if parsed.password:
            auth = f"{auth}:{parsed.password}"
        auth = f"{auth}@"
    path = parsed.path or ""
    return urlunsplit((scheme, f"{auth}{host}:{port}", path, parsed.query, parsed.fragment)).rstrip("/")


def _sticky_ollama_url() -> str | None:
    """Last known-good URL written by scripts/ensure-ollama-wsl.ps1 or a prior success."""
    env = (os.getenv("OLLAMA_BASE_URL") or "").strip()
    if env:
        return env.rstrip("/")
    # Repo root markers (WSL: /mnt/c/WebTrerm, Windows: C:\WebTrerm)
    candidates = [
        Path(os.getcwd()) / ".ollama_wsl_url",
        Path(__file__).resolve().parents[2] / ".ollama_wsl_url",
        Path("/mnt/c/WebTrerm/.ollama_wsl_url"),
        Path("C:/WebTrerm/.ollama_wsl_url"),
    ]
    for path in candidates:
        try:
            if path.is_file():
                value = path.read_text(encoding="utf-8", errors="ignore").strip()
                if value:
                    return value.rstrip("/")
        except OSError:
            continue
    return None


def remember_ollama_url(base_url: str) -> None:
    """Persist a working Ollama URL so the next request tries it first."""
    url = (base_url or "").strip().rstrip("/")
    if not url or "://" not in url:
        return
    for path in (
        Path(__file__).resolve().parents[2] / ".ollama_wsl_url",
        Path("/mnt/c/WebTrerm/.ollama_wsl_url"),
        Path("C:/WebTrerm/.ollama_wsl_url"),
    ):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(url + "\n", encoding="utf-8")
            return
        except OSError:
            continue


def _wsl_host_candidates() -> list[str]:
    """Windows host addresses as seen from WSL/Docker."""
    hosts: list[str] = []
    # Sticky / env first (survives WSL gateway IP churn)
    sticky = _sticky_ollama_url()
    if sticky:
        host = (urlsplit(sticky if "://" in sticky else f"http://{sticky}").hostname or "").strip()
        if host:
            hosts.append(host)
    env_host = (os.getenv("OLLAMA_HOST_IP") or os.getenv("WSL_HOST_IP") or "").strip()
    if env_host:
        hosts.insert(0, env_host.split(":")[0])

    hosts.extend(
        [
            "host.docker.internal",
            "host.containers.internal",
        ]
    )
    # WSL2 DNS / default gateway usually points at the Windows host
    try:
        for line in Path("/etc/resolv.conf").read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("nameserver "):
                candidate = (line.split(maxsplit=1)[1] or "").strip()
                if candidate and not candidate.startswith("127."):
                    hosts.append(candidate)
                break
    except OSError:
        pass
    try:
        for line in Path("/proc/net/route").read_text(encoding="utf-8", errors="ignore").splitlines()[1:]:
            parts = line.split()
            if len(parts) < 3 or parts[1] != "00000000":
                continue
            gateway_hex = parts[2]
            if len(gateway_hex) != 8:
                continue
            octets = [str(int(gateway_hex[i : i + 2], 16)) for i in range(0, 8, 2)]
            hosts.append(".".join(reversed(octets)))
            break
    except OSError:
        pass
    # Dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for h in hosts:
        if h and h not in seen:
            seen.add(h)
            out.append(h)
    return out


def _tcp_open(host: str, port: int, timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def get_ollama_base_urls(primary: str) -> list[str]:
    """Build candidate Ollama base URLs; prefer ones that accept TCP now.

    When running under WSL and Ollama is on Windows, 127.0.0.1 inside Linux
    is wrong — we try Windows host IPs. If a hard-coded primary dies (WSL
    gateway IP churn), still fall through to fresh candidates.
    """
    primary = normalize_ollama_base_url(primary)
    sticky = _sticky_ollama_url()
    parsed = urlsplit(primary)
    primary_host = (parsed.hostname or "").strip().lower()

    ordered: list[str] = []
    if sticky:
        ordered.append(normalize_ollama_base_url(sticky))
    ordered.append(primary)
    # Always keep localhost attempts (native Windows backend, or Ollama-in-WSL)
    for local in ("127.0.0.1", "localhost"):
        if local != primary_host:
            ordered.append(replace_ollama_host(primary, local))

    if is_wsl_runtime() or primary_host not in {"127.0.0.1", "localhost", "::1"}:
        for host in _wsl_host_candidates():
            url = replace_ollama_host(primary, host)
            if url not in ordered:
                ordered.append(url)

    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for url in ordered:
        if url in seen:
            continue
        seen.add(url)
        unique.append(url)

    # Fast TCP probe: put reachable URLs first (silent if all fail — caller retries)
    reachable: list[str] = []
    unreachable: list[str] = []
    for url in unique:
        host = (urlsplit(url).hostname or "").strip()
        p = urlsplit(url).port or 11434
        if host and _tcp_open(host, p):
            reachable.append(url)
        else:
            unreachable.append(url)
    if reachable:
        remember_ollama_url(reachable[0])
        return reachable + unreachable
    return unique
