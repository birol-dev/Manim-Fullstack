"""Origin policy for HTTP requests and the render WebSocket.

The render socket runs arbitrary Python, so a web page on another origin must
not be able to drive this server from the user's browser.

* Origin: requests without one (curl, scripts) are fine. A browser origin is
  allowed when it is listed in MANIM_ALLOWED_ORIGINS (comma separated, "*"
  allows all), or when it is loopback on the same port as the Host header or
  on a dev port (MANIM_DEV_ORIGIN_PORTS, default ``5173,8000`` — Vite and the
  app). Other localhost ports are not trusted.
* Host: must be a loopback name, or the host of an allowed origin. IP-address
  hosts are accepted only when MANIM_ALLOW_LAN=1. This stops DNS rebinding,
  where a hostile domain resolves to 127.0.0.1 and then makes "same-origin"
  requests that carry no Origin header.
* Peer: the TCP client must be loopback unless MANIM_ALLOW_LAN=1. Docker is
  exempt because published ports arrive from the bridge; bind those ports to
  127.0.0.1 on the host.
"""

import ipaddress
import os
from typing import Optional
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


def _header_port(host_header: str) -> Optional[int]:
    """Explicit port from a Host header, or None when the header omits it."""
    host = host_header.strip().lower()
    if host.startswith("["):
        end = host.find("]")
        rest = host[end + 1 :] if end != -1 else ""
        if rest.startswith(":") and rest[1:].isdigit():
            return int(rest[1:])
        return None
    if host.count(":") == 1:
        _, _, port = host.partition(":")
        if port.isdigit():
            return int(port)
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
    """Hostname from a Host header value ("[::1]:8000" -> "::1", "a.b:80" -> "a.b")."""
    host = host_header.strip().lower()
    if host.startswith("["):
        return host[1 : host.find("]")] if "]" in host else host
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def is_host_allowed(host_header: Optional[str]) -> bool:
    if not host_header:
        return True
    hostname = _hostname(host_header)
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
