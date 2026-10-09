"""Origin policy for HTTP requests and the render WebSocket.

The render socket runs arbitrary Python, so a web page on another origin must
not be able to drive this server from the user's browser.

* Origin: requests without one (curl, scripts) are fine. A browser origin is
  allowed when it is listed in MANIM_ALLOWED_ORIGINS (comma separated, "*"
  allows all), or when it is loopback on the same port as the Host header or
  on a dev port (MANIM_DEV_ORIGIN_PORTS, default ``5173,8000`` — Vite and the
  app). Other localhost ports are not trusted.
* Host: must be a well-formed ``host[:port]`` (port 1-65535) naming a loopback
  host or the host of an allowed origin. IP-address hosts are accepted only when
  MANIM_ALLOW_LAN=1. A malformed or empty Host is refused. This stops DNS rebinding,
  where a hostile domain resolves to 127.0.0.1 and then makes "same-origin"
  requests that carry no Origin header.
* Peer: the TCP client must be loopback unless MANIM_ALLOW_LAN=1. Docker is
  exempt because published ports arrive from the bridge; bind those ports to
  127.0.0.1 on the host.
"""

import ipaddress
import os
import re
from typing import Optional, Tuple
from urllib.parse import urlparse

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
# Vite's dev server, and the port run.py listens on. A page on any other
# localhost port must be listed in MANIM_ALLOWED_ORIGINS or MANIM_DEV_ORIGIN_PORTS.
DEFAULT_DEV_ORIGIN_PORTS = "5173,8000"


def configured_origins() -> set:
    raw = os.environ.get("MANIM_ALLOWED_ORIGINS", "")
    return {part.strip().rstrip("/").lower() for part in raw.split(",") if part.strip()}


def lan_enabled() -> bool:
    return os.environ.get("MANIM_ALLOW_LAN", "").lower() in ("1", "true", "yes")


def dev_origin_ports() -> set:
    raw = os.environ.get("MANIM_DEV_ORIGIN_PORTS", DEFAULT_DEV_ORIGIN_PORTS)
    ports = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ports.add(int(part))
    return ports


def _is_loopback_host(hostname: str) -> bool:
    if hostname in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _is_ip_literal(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        return False


def _origin_port(parsed) -> Optional[int]:
    port = parsed.port  # ValueError for a non-numeric or out-of-range port
    if port:
        return port
    if parsed.scheme == "https":
        return 443
    if parsed.scheme == "http":
        return 80
    return None


_DNS_LABEL = re.compile(r"^(?!-)[a-z0-9_-]{1,63}(?<!-)$")
_PORT = re.compile(r"^[0-9]{1,5}$")


def parse_host_header(host_header: Optional[str]) -> Tuple[str, Optional[int]]:
    """Split a Host header into (hostname, port or None); ValueError when malformed.

    Accepted: ``name``, ``name:port``, ``a.b.c.d[:port]``, ``[ipv6][:port]``, where
    a name is DNS labels (letters, digits, ``-``, ``_``; an optional trailing dot)
    and a port is 1-65535. Refused: an empty value, whitespace or controls inside,
    an empty port (``127.0.0.1:``), a non-numeric or out-of-range port, junk after
    the port (``127.0.0.1:8100.evil.com``), bare IPv6 without brackets, and
    userinfo or path characters.
    """
    if host_header is None:
        raise ValueError("no Host header")
    host = host_header.strip().lower()
    if not host or any(ord(ch) <= 0x20 or ord(ch) >= 0x7F for ch in host):
        raise ValueError("empty or non-printable Host")
    if host.startswith("["):
        end = host.find("]")
        if end == -1:
            raise ValueError("unclosed IPv6 literal")
        hostname = host[1:end]
        ipaddress.IPv6Address(hostname)  # ValueError for junk (and zone ids)
        rest = host[end + 1 :]
    else:
        if host.count(":") > 1:
            raise ValueError("IPv6 hosts need brackets")
        hostname, sep, port_text = host.partition(":")
        rest = sep + port_text
        name = hostname[:-1] if hostname.endswith(".") else hostname
        if not name or len(name) > 253 or not all(_DNS_LABEL.match(label) for label in name.split(".")):
            raise ValueError("invalid host name")
    if not rest:
        return hostname, None
    if not rest.startswith(":") or not _PORT.match(rest[1:]):
        raise ValueError("invalid port")
    port = int(rest[1:])
    if not 1 <= port <= 65535:
        raise ValueError("port out of range")
    return hostname, port


def _header_port(host_header: str) -> Optional[int]:
    """Explicit port from a Host header, or None when it omits one or is malformed."""
    try:
        return parse_host_header(host_header)[1]
    except ValueError:
        return None


def _loopback_origin_allowed(parsed, host_header: Optional[str]) -> bool:
    """Loopback pages may call the API only from the server's own port or a dev port."""
    origin_port = _origin_port(parsed)
    if origin_port in dev_origin_ports():
        return True
    if host_header:
        host_port = _header_port(host_header)
        if host_port is not None and origin_port == host_port:
            return True
    return False


def is_origin_allowed(origin: Optional[str], host_header: Optional[str] = None) -> bool:
    """True when a request carrying *origin* may be served. Malformed origins are refused."""
    try:
        return _origin_allowed(origin, host_header)
    except ValueError:
        # urlparse rejects e.g. "http://[::1" and ports like ":99999" or ":abc".
        return False


def _origin_allowed(origin: Optional[str], host_header: Optional[str]) -> bool:
    if not origin:
        return True
    normalized = origin.strip().rstrip("/").lower()
    configured = configured_origins()
    if "*" in configured or normalized in configured:
        return True
    parsed = urlparse(normalized)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    if _is_loopback_host(parsed.hostname):
        return _loopback_origin_allowed(parsed, host_header)
    if host_header and parsed.netloc == host_header.strip().lower():
        return lan_enabled() and _is_ip_literal(parsed.hostname)
    return False


def _hostname(host_header: str) -> str:
    """Hostname from a Host header value ("[::1]:8000" -> "::1", "a.b:80" -> "a.b");
    ValueError when the header is malformed."""
    return parse_host_header(host_header)[0]


def is_host_allowed(host_header: Optional[str]) -> bool:
    """True when a request with this Host header may be served.

    No header at all (HTTP/1.0 clients, in-process test clients) passes; an empty
    or malformed one is refused.
    """
    if host_header is None:
        return True
    try:
        hostname = _hostname(host_header)
    except ValueError:
        return False
    if _is_loopback_host(hostname):
        return True
    if _is_ip_literal(hostname):
        return lan_enabled()
    configured = configured_origins()
    if "*" in configured:
        return True
    return any(_configured_hostname(origin) == hostname for origin in configured)


def _configured_hostname(origin: str) -> Optional[str]:
    try:
        return urlparse(origin).hostname
    except ValueError:
        return None


def is_peer_allowed(peer: Optional[str]) -> bool:
    """True when the TCP client may talk to this server.

    ``testclient`` is Starlette's TestClient. Docker port-proxying always
    presents the bridge address, so the container cannot tell a localhost
    publish from a public one — publish on 127.0.0.1 instead.
    """
    if not peer or peer == "testclient":
        return True
    if _is_loopback_host(peer):
        return True
    if lan_enabled():
        return True
    if os.environ.get("RUNNING_IN_DOCKER", "").lower() == "true":
        return True
    return False
