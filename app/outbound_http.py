"""Fail-closed outbound HTTP client with DNS pinning and redirect revalidation."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Collection, Mapping, Sequence
from typing import Any

import httpx

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_SENSITIVE_REDIRECT_HEADERS = {"authorization", "cookie", "proxy-authorization"}
_ENTITY_HEADERS = {"content-encoding", "content-language", "content-length", "content-location", "content-type"}

AddressResolver = Callable[[str, int], Awaitable[Sequence[str]]]


class OutboundHTTPPolicyError(RuntimeError):
    """Raised before a request can reach a destination denied by egress policy."""


async def _resolve_host_addresses(host: str, port: int) -> list[str]:
    def _lookup() -> list[str]:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
        return sorted({str(record[4][0]).split("%", 1)[0] for record in records})

    try:
        return await asyncio.to_thread(_lookup)
    except OSError as exc:
        raise OutboundHTTPPolicyError("Outbound HTTP destination could not be resolved") from exc


def _is_public_unicast(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return _is_public_unicast(address.ipv4_mapped)
    return bool(
        address.is_global
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_private
        and not address.is_reserved
        and not address.is_unspecified
    )


async def validate_outbound_http_target(
    url: str | httpx.URL,
    resolver: AddressResolver | None = None,
    *,
    allow_private: bool = False,
    allowed_hosts: Collection[str] | None = None,
) -> tuple[httpx.URL, httpx.URL, str]:
    try:
        logical_url = httpx.URL(url)
    except (TypeError, ValueError) as exc:
        raise OutboundHTTPPolicyError("Outbound HTTP URL is invalid") from exc

    if logical_url.scheme not in {"http", "https"} or not logical_url.host:
        raise OutboundHTTPPolicyError("Outbound HTTP requires an http or https URL")
    if logical_url.userinfo:
        raise OutboundHTTPPolicyError("Outbound HTTP URLs cannot contain credentials")

    default_port = 443 if logical_url.scheme == "https" else 80
    port = logical_url.port or default_port
    host = logical_url.host.rstrip(".").lower()
    if not host:
        raise OutboundHTTPPolicyError("Outbound HTTP URL has no destination host")
    if allowed_hosts is not None:
        normalized_allowed_hosts = {
            str(allowed_host).strip().rstrip(".").lower()
            for allowed_host in allowed_hosts
            if str(allowed_host).strip()
        }
        if host not in normalized_allowed_hosts:
            raise OutboundHTTPPolicyError("Outbound HTTP destination host is not allowed")

    try:
        direct_address = ipaddress.ip_address(host)
    except ValueError:
        addresses = await (resolver or _resolve_host_addresses)(host, port)
    else:
        addresses = [str(direct_address)]

    if not addresses:
        raise OutboundHTTPPolicyError("Outbound HTTP destination could not be resolved")

    parsed_addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    public_classes: set[bool] = set()
    for raw_address in addresses:
        try:
            address = ipaddress.ip_address(str(raw_address).split("%", 1)[0])
        except ValueError as exc:
            raise OutboundHTTPPolicyError("Outbound HTTP resolver returned an invalid address") from exc
        is_public = _is_public_unicast(address)
        allowed_private = bool(
            allow_private
            and (address.is_private or address.is_loopback)
            and not address.is_link_local
            and not address.is_multicast
            and not address.is_unspecified
        )
        if not is_public and not allowed_private:
            raise OutboundHTTPPolicyError("Outbound HTTP destination is blocked by policy")
        parsed_addresses.append(address)
        public_classes.add(is_public)

    if len(public_classes) > 1:
        raise OutboundHTTPPolicyError("Outbound HTTP destination returned mixed public and private addresses")

    pinned_address = sorted(parsed_addresses, key=lambda item: (item.version, int(item)))[0]
    pinned_url = logical_url.copy_with(host=str(pinned_address), port=logical_url.port)
    host_header = logical_url.netloc.decode("ascii")
    return logical_url, pinned_url, host_header


async def prepare_outbound_http_request(
    url: str | httpx.URL,
    headers: Mapping[str, str] | httpx.Headers | None = None,
    *,
    allow_private: bool = False,
    allowed_hosts: Collection[str] | None = None,
) -> tuple[httpx.URL, httpx.Headers, dict[str, str | None]]:
    logical_url, pinned_url, host_header = await validate_outbound_http_target(
        url,
        allow_private=allow_private,
        allowed_hosts=allowed_hosts,
    )
    secured_headers = httpx.Headers(headers or {})
    secured_headers["Host"] = host_header
    return pinned_url, secured_headers, {"sni_hostname": logical_url.host}


def _redirect_method(method: str, status_code: int) -> str:
    if status_code == 303 and method != "HEAD":
        return "GET"
    if status_code in {301, 302} and method == "POST":
        return "GET"
    return method


def _redirect_headers(headers: httpx.Headers, previous: httpx.URL, next_url: httpx.URL, method: str) -> httpx.Headers:
    next_headers = httpx.Headers(headers)
    if (previous.scheme, previous.host, previous.port) != (next_url.scheme, next_url.host, next_url.port):
        for header in _SENSITIVE_REDIRECT_HEADERS:
            next_headers.pop(header, None)
    if method in {"GET", "HEAD"}:
        for header in _ENTITY_HEADERS:
            next_headers.pop(header, None)
    return next_headers


async def request_outbound_http(
    method: str,
    url: str,
    *,
    timeout: int | float,
    headers: Mapping[str, str] | httpx.Headers | None = None,
    max_redirects: int = 0,
    client_factory: Callable[..., Any] | None = None,
    resolver: AddressResolver | None = None,
    allow_private: bool = False,
    allowed_hosts: Collection[str] | None = None,
    **request_kwargs: Any,
) -> httpx.Response:
    """Request a public destination through a DNS-pinned, proxy-free connection.

    Every hop is parsed and resolved before the client is created or the request is
    sent. The validated address replaces the connection host, while Host and TLS
    SNI retain the logical hostname for virtual hosting and certificate checks.
    """

    request_method = str(method or "GET").strip().upper()
    if not request_method:
        raise OutboundHTTPPolicyError("Outbound HTTP method is required")
    redirect_limit = max(0, min(int(max_redirects), 10))
    factory = client_factory or httpx.AsyncClient
    logical_url, pinned_url, host_header = await validate_outbound_http_target(
        url,
        resolver,
        allow_private=allow_private,
        allowed_hosts=allowed_hosts,
    )
    request_headers = httpx.Headers(headers or {})
    request_payload = dict(request_kwargs)

    async with factory(timeout=timeout, follow_redirects=False, trust_env=False) as client:
        for redirect_count in range(redirect_limit + 1):
            hop_headers = httpx.Headers(request_headers)
            hop_headers["Host"] = host_header
            extensions = dict(request_payload.get("extensions") or {})
            extensions["sni_hostname"] = logical_url.host
            hop_kwargs = {**request_payload, "headers": hop_headers, "extensions": extensions}
            response = await client.request(request_method, pinned_url, **hop_kwargs)

            location = response.headers.get("location") if response.status_code in _REDIRECT_STATUSES else None
            if not location:
                return response
            if redirect_count >= redirect_limit:
                raise OutboundHTTPPolicyError("Outbound HTTP redirect limit exceeded")

            next_logical = logical_url.join(location)
            next_method = _redirect_method(request_method, response.status_code)
            request_headers = _redirect_headers(request_headers, logical_url, next_logical, next_method)
            if next_method in {"GET", "HEAD"} and next_method != request_method:
                for key in ("content", "data", "files", "json"):
                    request_payload.pop(key, None)
            request_method = next_method
            logical_url, pinned_url, host_header = await validate_outbound_http_target(
                next_logical,
                resolver,
                allow_private=allow_private,
                allowed_hosts=allowed_hosts,
            )

    raise OutboundHTTPPolicyError("Outbound HTTP request did not produce a response")
