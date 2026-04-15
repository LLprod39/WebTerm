"""
Guacamole protocol tunnel to guacd for RDP in browser.

Flow:
1. Connect to guacd, send "select" (rdp), receive "args".
2. Send "args" to client (browser).
3. Client sends handshake (size, audio, image, connect); we buffer and do not forward.
4. Send our "connect" to guacd with host/port/username/password.
5. Forward guacd "ready" and all following data to client.
6. Proxy client <-> guacd bidirectionally.
"""

from __future__ import annotations

import asyncio
import re

from django.conf import settings
from loguru import logger


def _guac_elem(s: str) -> str:
    """Format one Guacamole instruction element: length.value"""
    return f"{len(s)}.{s}"


def _guac_instruction(opcode: str, *args: str) -> str:
    """Build one Guacamole instruction: OPCODE,arg1,arg2,...;"""
    parts = [_guac_elem(opcode)]
    for a in args:
        parts.append(_guac_elem(str(a)))
    return ",".join(parts) + ";"


def _parse_guac_instruction(data: str) -> list[str]:
    """
    Parse one Guacamole instruction: LENGTH.VALUE,LENGTH.VALUE,...;
    Returns list of values (without length prefix).
    """
    values = []
    i = 0
    while i < len(data):
        if data[i] == ";":
            break
        dot = data.find(".", i)
        if dot == -1:
            break
        try:
            length = int(data[i:dot])
        except ValueError:
            break
        start = dot + 1
        end = start + length
        if end > len(data):
            break
        values.append(data[start:end])
        i = end
        if i < len(data) and data[i] == ",":
            i += 1
    return values


def _find_connect_end(data: str) -> int:
    """
    Find the end of the first 'connect' instruction in Guacamole stream.
    Returns index of the semicolon that ends the connect instruction, or -1.
    """
    m = re.search(r"\d+\.connect,", data)
    if not m:
        return -1
    start = m.start()
    pos = data.find(";", start)
    return pos if pos != -1 else -1


def _connect_values_from_args(param_names: list[str], host: str, port: int, username: str, password: str, domain: str = "", ignore_cert: bool = True) -> list[str]:
    """Build connect instruction values in the order expected by guacd (from args)."""
    # Map known RDP parameter names to our values
    value_map = {
        "hostname": host,
        "port": str(port),
        "username": username,
        "password": password or "",
        "domain": domain or "",
        "ignore-cert": "true" if ignore_cert else "false",
        "security": "any",
        "disable-auth": "",
        "enable-drive": "false",
        "drive-path": "",
        "disable-wallpaper": "true",
        "enable-theming": "false",
        "resize-method": "display-update",
        "width": "1024",
        "height": "768",
        "dpi": "96",
    }
    return [value_map.get(p, "") for p in param_names]


async def guacd_rdp_handshake(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    host: str,
    port: int,
    username: str,
    password: str,
    domain: str = "",
    ignore_cert: bool = True,
) -> str:
    """
    Perform handshake with guacd for RDP. Send select(rdp), read args,
    send size/audio/image/connect. Return the received 'args' line (to forward to client).
    """
    writer.write(_guac_instruction("select", "rdp").encode("utf-8"))
    await writer.drain()

    buf = b""
    args_line: str | None = None
    while True:
        chunk = await reader.read(4096)
        if not chunk:
            raise ConnectionError("guacd closed before args")
        buf += chunk
        text = buf.decode("utf-8", errors="replace")
        if "args" in text and ";" in text:
            idx = text.find("args")
            if idx >= 0:
                back = text.rfind(";", 0, idx) + 1
                start = back if back > 0 else 0
                end = text.index(";", idx) + 1
                args_line = text[start:end]
            break

    if not args_line:
        raise ValueError("No args from guacd")

    # Parse args: first element is opcode "args", second is version, rest are parameter names
    parts = _parse_guac_instruction(args_line)
    if not parts:
        param_names = ["hostname", "port", "username", "password", "domain", "ignore-cert"]
        version = "VERSION_1_1_0"
    elif len(parts) == 1:
        version = "VERSION_1_1_0"
        param_names = ["hostname", "port", "username", "password"]
    else:
        version = parts[1]
        param_names = parts[2:] if len(parts) > 2 else ["hostname", "port", "username", "password"]

    connect_vals = [version] + _connect_values_from_args(param_names, host, port, username, password, domain, ignore_cert)
    writer.write(
        (
            _guac_instruction("size", "1024", "768", "96")
            + _guac_instruction("audio")
            + _guac_instruction("video")
            + _guac_instruction("image", "image/png", "image/jpeg")
            + _guac_instruction("connect", *connect_vals)
        ).encode("utf-8")
    )
    await writer.drain()

    return args_line


async def connect_guacd_rdp(
    host: str,
    port: int,
    username: str,
    password: str,
    domain: str = "",
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter, str]:
    """
    Connect to guacd, perform RDP handshake. Returns (reader, writer, args_to_send_to_client).
    Caller must send args_to_send_to_client to the browser first, then forward ready and rest.
    """
    guacd_host = getattr(settings, "GUACD_HOST", "127.0.0.1")
    guacd_port = getattr(settings, "GUACD_PORT", 4822)
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(guacd_host, guacd_port),
            timeout=10,
        )
    except (OSError, asyncio.TimeoutError) as e:
        logger.warning("guacd connection failed: {}", e)
        raise ConnectionError(f"guacd unreachable: {e}") from e

    try:
        args_line = await guacd_rdp_handshake(
            reader, writer,
            host=host, port=port, username=username, password=password,
            domain=domain, ignore_cert=True,
        )
    except Exception:
        writer.close()
        await writer.wait_closed()
        raise
    return reader, writer, args_line
