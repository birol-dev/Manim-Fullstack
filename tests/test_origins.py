import pytest
from starlette.websockets import WebSocketDisconnect
from unittest.mock import patch

import main
from origins import is_origin_allowed


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "",
        "http://localhost:5173",
        "http://localhost",
        "https://127.0.0.1:8000",
        "http://[::1]:3000",
        "http://app.localhost:8080",
    ],
)
def test_local_and_missing_origins_are_allowed(origin):
    assert is_origin_allowed(origin, "localhost:8000") is True


@pytest.mark.parametrize(
    "origin",
    ["https://evil.example", "http://localhost.evil.example", "null", "file://", "chrome-extension://abc"],
)
def test_foreign_origins_are_rejected(origin, monkeypatch):
    monkeypatch.delenv("MANIM_ALLOWED_ORIGINS", raising=False)
    assert is_origin_allowed(origin, "localhost:8000") is False


def test_same_origin_by_ip_allowed_but_not_by_hostname(monkeypatch):
    monkeypatch.delenv("MANIM_ALLOWED_ORIGINS", raising=False)
    # LAN access by IP address is fine.
    assert is_origin_allowed("http://192.168.1.20:8000", "192.168.1.20:8000") is True
    # A hostname matching its own Host header could be DNS rebinding.
    assert is_origin_allowed("http://rebind.example:8000", "rebind.example:8000") is False


def test_configured_origins(monkeypatch):
    monkeypatch.setenv("MANIM_ALLOWED_ORIGINS", "https://studio.example.com/, https://other.example")
    assert is_origin_allowed("https://studio.example.com", "api.example.com") is True
    assert is_origin_allowed("https://other.example/", None) is True
    assert is_origin_allowed("https://third.example", None) is False

    monkeypatch.setenv("MANIM_ALLOWED_ORIGINS", "*")
    assert is_origin_allowed("https://anything.example", None) is True


def test_http_requests_from_foreign_origin_are_blocked(client, tmp_path, monkeypatch):
    monkeypatch.delenv("MANIM_ALLOWED_ORIGINS", raising=False)
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)):
        blocked = client.post(
            "/api/save",
            json={"filename": "pwned.py", "code": "print(1)"},
            headers={"Origin": "https://evil.example"},
        )
        assert blocked.status_code == 403
        assert not (tmp_path / "pwned.py").exists()

        allowed = client.post(
            "/api/save",
            json={"filename": "ok.py", "code": "print(1)"},
            headers={"Origin": "http://localhost:5173"},
        )
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_websocket_from_foreign_origin_is_refused(client, monkeypatch):
    monkeypatch.delenv("MANIM_ALLOWED_ORIGINS", raising=False)
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/api/render", headers={"Origin": "https://evil.example"}) as ws:
            ws.receive_json()
    assert excinfo.value.code == 1008

    with client.websocket_connect("/api/render", headers={"Origin": "http://localhost:8000"}) as ws:
        ws.send_text("not json")
        assert ws.receive_json()["type"] == "error"
