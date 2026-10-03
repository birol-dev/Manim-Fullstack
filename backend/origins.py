"""Origin policy for HTTP requests and the render WebSocket.

The render socket runs arbitrary Python, so a web page on another origin must
not be able to drive this server from the user's browser.

* Origin: requests without one (curl, scripts) are fine; otherwise it must be a
  loopback origin (localhost dev servers), the server's own origin when it is
  addressed by IP (LAN use), or listed in MANIM_ALLOWED_ORIGINS (comma
  separated, "*" allows all).
* Host: must be a loopback name, an IP address, or the host of an allowed
  origin. This stops DNS rebinding, where a hostile domain resolves to
  127.0.0.1 and then makes "same-origin" requests that carry no Origin header.
"""

import ipaddress
import os
from typing import Optional
from urllib.parse import urlparse

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def configured_origins() -> set:
    raw = os.environ.get("MANIM_ALLOWED_ORIGINS", "")
    return {part.strip().rstrip("/").lower() for part in raw.split(",") if part.strip()}


def _is_loopback_host(hostname: str) -> bool:
    if hostname in LOOPBACK_HOSTS or hostname.endswith(".localhost"):
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


def is_origin_allowed(origin: Optional[str], host_header: Optional[str] = None) -> bool:
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
        return True
    if host_header and parsed.netloc == host_header.strip().lower():
        return _is_ip_literal(parsed.hostname)
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
    if _is_loopback_host(hostname) or _is_ip_literal(hostname):
        return True
    configured = configured_origins()
    if "*" in configured:
        return True
    return any(urlparse(origin).hostname == hostname for origin in configured)
