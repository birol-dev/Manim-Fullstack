"""Fix round 4: strict Host header parsing (port 1-65535, no junk after the port)."""

import pytest

from origins import is_host_allowed, is_origin_allowed, parse_host_header

REFUSED = [
    "",
    "   ",
    "127.0.0.1:8100.evil.com",
    "localhost:8100.evil.com",
    "localhost:abc",
    "localhost:65536",
    "localhost:99999",
    "localhost:0",
    "localhost:-1",
    "localhost:+80",
    "localhost:８１００",  # fullwidth digits
    "127.0.0.1:",
    "[::1]:",
    "[::1",
    "[::1]x",
    "[::1]:80:80",
    "[not-an-ip]:80",
    "[fe80::1%eth0]:80",
    "::1",  # bare IPv6 needs brackets in a Host header
    "127.0.0.1 :8100",
    "127.0.0.1: 8100",
    "local host:8100",
    "localhost\t:8100",
    "localhost:8100:8100",
    "user@localhost:8100",
    "localhost/path",
    "localhost?x",
    "localhost#x",
    "localhost\\x",
    "-localhost",
    "localhost..",
    "lo..calhost",
    "évil.localhost",
    "localhost\x00",
    "a" * 64 + ".localhost",
    "evil.com",
    "evil.com:8100",
    "192.168.1.5:8100",  # IP hosts need MANIM_ALLOW_LAN
]

ALLOWED = [
    None,  # no Host at all (HTTP/1.0, in-process clients)
    "localhost",
    "localhost:8100",
    "LOCALHOST:8100",
    "LocalHost",
    "127.0.0.1",
    "127.0.0.1:8100",
    "127.0.0.1:1",
    "127.0.0.1:65535",
    "127.0.0.1:08100",
    "127.0.0.2:5180",
    "[::1]",
    "[::1]:8100",
    "[0:0:0:0:0:0:0:1]:8100",
    " localhost:8100 ",  # optional whitespace around a header value
]


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    monkeypatch.delenv("MANIM_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("MANIM_ALLOW_LAN", raising=False)
    monkeypatch.delenv("MANIM_DEV_ORIGIN_PORTS", raising=False)


@pytest.mark.parametrize("host", REFUSED)
def test_malformed_or_foreign_hosts_are_refused(host):
    assert is_host_allowed(host) is False


@pytest.mark.parametrize("host", ALLOWED)
def test_legitimate_loopback_hosts_still_work(host):
    assert is_host_allowed(host) is True


def test_parse_host_header_splits_name_and_port():
    assert parse_host_header("LOCALHOST:8100") == ("localhost", 8100)
    assert parse_host_header("[::1]:5180") == ("::1", 5180)
    assert parse_host_header("[::1]") == ("::1", None)
    assert parse_host_header("studio.example.com.") == ("studio.example.com.", None)
    for bad in ("127.0.0.1:8100.evil.com", "localhost:", "localhost:0", "localhost:65536", ""):
        with pytest.raises(ValueError):
            parse_host_header(bad)


def test_lan_mode_accepts_ip_hosts_with_valid_ports_only(monkeypatch):
    monkeypatch.setenv("MANIM_ALLOW_LAN", "1")
    assert is_host_allowed("192.168.1.5:8100") is True
    assert is_host_allowed("192.168.1.5") is True
    assert is_host_allowed("192.168.1.5:") is False
    assert is_host_allowed("192.168.1.5:8100.evil.com") is False
    assert is_host_allowed("192.168.1.5:70000") is False


def test_configured_origin_hosts(monkeypatch):
    monkeypatch.setenv("MANIM_ALLOWED_ORIGINS", "https://studio.example.com")
    assert is_host_allowed("studio.example.com") is True
    assert is_host_allowed("STUDIO.example.com:443") is True
    assert is_host_allowed("studio.example.com:443.evil") is False
    assert is_host_allowed("studio.example.com:") is False
    monkeypatch.setenv("MANIM_ALLOWED_ORIGINS", "*")
    assert is_host_allowed("anything.example:8080") is True
    assert is_host_allowed("anything.example:8080x") is False


def test_origin_port_comparison_uses_the_strict_parser():
    # Own port: the Origin's port must equal a valid Host port.
    assert is_origin_allowed("http://localhost:8100", "localhost:8100") is True
    assert is_origin_allowed("http://localhost:8100", "[::1]:8100") is True
    assert is_origin_allowed("http://localhost:8100", "localhost:8100.evil.com") is False
    assert is_origin_allowed("http://localhost:5173", "localhost:8100") is True  # dev port
    assert is_origin_allowed("http://localhost:5180", "localhost:8100") is False


@pytest.mark.parametrize(
    "host,status",
    [
        ("localhost:8100", 200),
        ("[::1]:8100", 200),
        ("LOCALHOST", 200),
        ("127.0.0.1:8100.evil.com", 403),
        ("localhost:abc", 403),
        ("127.0.0.1:", 403),
        ("", 403),
        ("localhost:65536", 403),
    ],
)
def test_http_requests_follow_the_host_policy(client, host, status):
    assert client.get("/api/health", headers={"host": host}).status_code == status


def test_websocket_handshake_follows_the_host_policy(client):
    from starlette.websockets import WebSocketDisconnect

    with client.websocket_connect("/api/render", headers={"host": "localhost:8100"}) as ws:
        ws.send_text("not json")
        assert ws.receive_json()["type"] == "error"
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/render", headers={"host": "127.0.0.1:8100.evil.com"}) as ws:
            ws.receive_json()
