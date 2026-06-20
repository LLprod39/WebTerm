from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

OLLAMA_CLOUD_MODEL_SUFFIX = " (cloud)"
OLLAMA_RUNTIME_MODES = {"auto", "local", "cloud"}
OLLAMA_THINK_MODES = {"", "off", "on", "low", "medium", "high"}


def normalize_ollama_base_url(raw: str | None = None) -> str:
    value = (
        (raw or "").strip()
        or (os.getenv("OLLAMA_BASE_URL") or "").strip()
        or "http://127.0.0.1:11434"
    ).rstrip("/")
    if "://" not in value:
        value = f"http://{value}"
    return value.rstrip("/")


def normalize_ollama_cloud_base_url(raw: str | None = None) -> str:
    value = (
        (raw or "").strip()
        or (os.getenv("OLLAMA_CLOUD_BASE_URL") or "").strip()
        or "https://ollama.com"
    ).rstrip("/")
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


def get_ollama_base_urls(primary: str) -> list[str]:
    urls: list[str] = [primary]
    parsed = urlsplit(primary)
    host = (parsed.hostname or "").strip().lower()

    if host not in {"127.0.0.1", "localhost", "::1"} or not is_wsl_runtime():
        return urls

    fallback_hosts: list[str] = ["host.docker.internal", "host.containers.internal"]
    try:
        for line in Path("/etc/resolv.conf").read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("nameserver "):
                candidate = (line.split(maxsplit=1)[1] or "").strip()
                if candidate:
                    fallback_hosts.append(candidate)
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
            octets = [str(int(gateway_hex[i:i + 2], 16)) for i in range(0, 8, 2)]
            fallback_hosts.append(".".join(reversed(octets)))
            break
    except OSError:
        pass

    seen_hosts: set[str] = set()
    for fallback_host in fallback_hosts:
        normalized_host = fallback_host.strip().lower()
        if not normalized_host or normalized_host in seen_hosts:
            continue
        seen_hosts.add(normalized_host)
        candidate_url = replace_ollama_host(primary, fallback_host.strip())
        if candidate_url not in urls:
            urls.append(candidate_url)
    return urls
