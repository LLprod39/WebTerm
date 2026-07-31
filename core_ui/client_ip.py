"""Trusted client IP extraction shared by audit and authentication paths."""

from __future__ import annotations

from ipaddress import ip_address

from django.conf import settings


def _normalized_ip(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return ip_address(raw).compressed
    except ValueError:
        return ""


def extract_client_ip(request, *, trusted_proxy_hops: int | None = None) -> str:
    """Return a validated client address without trusting the left edge of XFF.

    ``REMOTE_ADDR`` is authoritative by default. Deployments behind known reverse
    proxies may opt into a fixed number of trusted hops; the address is then
    selected from the right-hand side of ``X-Forwarded-For`` so client-supplied
    values on the left cannot override it.
    """

    if request is None:
        return ""

    remote_addr = _normalized_ip(request.META.get("REMOTE_ADDR"))
    if trusted_proxy_hops is None:
        trusted_proxy_hops = int(getattr(settings, "TRUSTED_PROXY_HOPS", 0) or 0)
    hops = max(0, min(int(trusted_proxy_hops), 16))
    if hops == 0:
        return remote_addr

    forwarded = [item.strip() for item in str(request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")]
    forwarded = [item for item in forwarded if item]
    if len(forwarded) < hops:
        return remote_addr

    return _normalized_ip(forwarded[-hops]) or remote_addr
