import pytest
from starlette.testclient import TestClient

import main
from studio.auth import COOKIE, agent_token


def test_desktop_session_protects_files_and_render_socket(monkeypatch):
    monkeypatch.setenv("MANIM_API_TOKEN", "desktop-secret")
    client = TestClient(main.app, base_url="http://localhost")
    assert client.get("/api/files").status_code == 401
    assert client.get("/api/desktop/session?token=wrong").status_code == 401
    paired = client.get("/api/desktop/session?token=desktop-secret", follow_redirects=False)
    assert paired.status_code == 303 and paired.headers["location"] == "/"
    assert "HttpOnly" in paired.headers["set-cookie"] and "SameSite=strict" in paired.headers["set-cookie"]
    assert COOKIE in client.cookies
    assert client.get("/api/studio/catalog").status_code == 200
    client.cookies.clear()
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("ws://localhost/api/render"):
            pass


def test_agent_credential_cannot_open_author_api(monkeypatch, tmp_path):
    monkeypatch.setenv("MANIM_API_TOKEN", "desktop-secret")
    monkeypatch.setenv("MANIM_MCP_TOKEN", "agent-secret")
    client = TestClient(main.app, base_url="http://localhost", headers={"Authorization": "Bearer agent-secret"})
    assert client.get("/api/studio/catalog").status_code == 200
    assert client.get("/api/files").status_code == 401
    assert agent_token(str(tmp_path)) == "agent-secret"


def test_mcp_requires_explicit_credential(monkeypatch):
    if main.studio_mcp is None:
        pytest.skip("MCP SDK not installed")
    monkeypatch.setenv("MANIM_MCP_TOKEN", "agent-secret")
    client = TestClient(main.app, base_url="http://localhost")
    assert client.post("/mcp/", json={}).status_code == 401
    client.cookies.set(COOKIE, "agent-secret")
    assert client.post("/mcp/", json={}).status_code == 401


def test_app_lifecycle_can_restart_with_mcp():
    for _ in range(2):
        with TestClient(main.app, base_url="http://localhost") as client:
            assert client.get("/api/health").status_code == 200
