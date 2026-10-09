"""Body-size middleware, origin/peer policy edge cases, media deletion, and request flags."""

import asyncio
import json
import os

import pytest
from unittest.mock import patch

import main
import origins
from origins import is_host_allowed, is_origin_allowed, is_peer_allowed


# --------------------------------------------------------------------------- #
# LimitCodeBodyMiddleware (raw ASGI, so disconnects can be simulated exactly)
# --------------------------------------------------------------------------- #


def _scope(path="/api/save", method="POST", headers=()):
    return {"type": "http", "path": path, "method": method, "headers": list(headers)}


class _Recorder:
    """Downstream app that reads the whole body, like FastAPI does."""

    def __init__(self):
        self.called = False
        self.body = b""
        self.extra = None

    async def __call__(self, scope, receive, send):
        self.called = True
        while True:
            message = await receive()
            self.body += message.get("body", b"")
            if not message.get("more_body", False):
                break
        if scope.get("read_extra"):
            self.extra = await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


def _run_middleware(scope, messages):
    downstream = _Recorder()
    middleware = main.LimitCodeBodyMiddleware(downstream)
    queue = list(messages)
    calls = {"receive": 0}
    sent = []

    async def receive():
        calls["receive"] += 1
        if calls["receive"] > 1000:
            raise AssertionError("middleware kept reading after the client disconnected")
        # After the scripted messages, behave like uvicorn: disconnect forever.
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    asyncio.run(middleware(scope, receive, send))
    return downstream, sent, calls["receive"]


def _status(sent):
    return next((m["status"] for m in sent if m["type"] == "http.response.start"), None)


def test_chunked_body_cut_off_mid_stream_ends_without_spinning():
    downstream, sent, reads = _run_middleware(
        _scope(),
        [{"type": "http.request", "body": b'{"a":', "more_body": True}, {"type": "http.disconnect"}],
    )
    # The route sees the disconnect once (FastAPI raises ClientDisconnect); nothing loops.
    assert downstream.called is True and downstream.body == b'{"a":'
    assert reads == 2


def test_chunked_body_over_the_limit_is_413_without_reading_the_rest(monkeypatch):
    monkeypatch.setattr(main, "MAX_REQUEST_BODY_BYTES", 10)
    chunk = b"x" * 4096
    downstream, sent, reads = _run_middleware(
        _scope(),
        [{"type": "http.request", "body": chunk, "more_body": True}] * 4,
    )
    assert _status(sent) == 413
    assert reads == 1  # cut off at the first chunk past the cap
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    assert b"exceeds maximum size" in body
    assert downstream.body == b""


def test_chunked_body_under_the_limit_streams_then_reads_pass_through():
    scope = {**_scope("/api/parse-code"), "read_extra": True}
    downstream, sent, _ = _run_middleware(
        scope,
        [
            {"type": "http.request", "body": b'{"code":', "more_body": True},
            {"type": "http.request", "body": b'"x"}', "more_body": False},
        ],
    )
    assert downstream.body == b'{"code":"x"}'
    # Reads after the body come from the real connection, not a fake disconnect.
    assert downstream.extra == {"type": "http.disconnect"}
    assert _status(sent) == 200


def test_huge_content_length_is_413_before_reading():
    downstream, sent, reads = _run_middleware(_scope(headers=[(b"content-length", str(10**9).encode())]), [])
    assert downstream.called is False and reads == 0
    assert _status(sent) == 413


@pytest.mark.parametrize(
    "headers",
    [
        [(b"content-length", b"not-a-number")],
        [(b"content-length", b"-5")],
        [(b"content-length", b"5"), (b"content-length", b"6")],
    ],
)
def test_bad_content_length_is_400_before_reading(headers):
    downstream, sent, reads = _run_middleware(_scope(headers=headers), [])
    assert downstream.called is False and reads == 0
    assert _status(sent) == 400


def test_content_length_with_transfer_encoding_is_refused():
    """CL + TE (request smuggling, and the r2 size-cap bypass): 400, nothing read."""
    downstream, sent, reads = _run_middleware(
        _scope(headers=[(b"content-length", b"10"), (b"transfer-encoding", b"chunked")]),
        [{"type": "http.request", "body": b"x" * 100, "more_body": False}],
    )
    assert downstream.called is False and reads == 0
    assert _status(sent) == 400
    assert (b"connection", b"close") in next(m for m in sent if m["type"] == "http.response.start")["headers"]


def test_every_body_route_is_capped_not_just_save(monkeypatch):
    monkeypatch.setattr(main, "MAX_REQUEST_BODY_BYTES", 10)
    downstream, sent, _ = _run_middleware(
        _scope("/api/rename"), [{"type": "http.request", "body": b"x" * 64, "more_body": True}]
    )
    assert _status(sent) == 413


def test_uploads_get_the_asset_cap():
    limit, message = main.RequestBodyLimitMiddleware.limit_for("/api/upload-asset")
    assert limit == main.MAX_ASSET_SIZE_BYTES + main.UPLOAD_OVERHEAD_BYTES and "50MB" in message
    assert main.RequestBodyLimitMiddleware.limit_for("/api/save")[0] == main.MAX_REQUEST_BODY_BYTES


def test_stalled_body_times_out_with_408(monkeypatch):
    monkeypatch.setattr(main, "BODY_READ_TIMEOUT_SECONDS", 0.05)
    downstream = _Recorder()
    middleware = main.RequestBodyLimitMiddleware(downstream)
    sent = []
    reads = []

    async def receive():
        reads.append(1)
        if len(reads) == 1:
            return {"type": "http.request", "body": b'{"a"', "more_body": True}
        await asyncio.sleep(5)  # the client stopped sending
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    async def run():
        await asyncio.wait_for(middleware(_scope(), receive, send), timeout=2)

    asyncio.run(run())
    assert _status(sent) == 408


def test_timeout_does_not_apply_after_the_body(monkeypatch):
    """Once the body is complete, a route waiting for the disconnect is not cut off."""
    monkeypatch.setattr(main, "BODY_READ_TIMEOUT_SECONDS", 0.01)
    scope = {**_scope("/api/parse-code"), "read_extra": True}

    downstream = _Recorder()
    middleware = main.RequestBodyLimitMiddleware(downstream)
    sent = []
    messages = [{"type": "http.request", "body": b"{}", "more_body": False}]

    async def receive():
        if messages:
            return messages.pop(0)
        await asyncio.sleep(0.1)
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    asyncio.run(middleware(scope, receive, send))
    assert _status(sent) == 200 and downstream.extra == {"type": "http.disconnect"}


def test_chunked_request_through_the_app_is_capped(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_REQUEST_BODY_BYTES", 1000)

    def body():
        for _ in range(10):
            yield b"x" * 500

    res = client.post("/api/rename", content=body(), headers={"content-type": "application/json"})
    assert res.status_code == 413 and "exceeds maximum size" in res.json()["detail"]


def test_honest_small_content_length_goes_straight_through():
    downstream, sent, _ = _run_middleware(
        _scope(headers=[(b"content-length", b"2")]),
        [{"type": "http.request", "body": b"{}", "more_body": False}],
    )
    assert downstream.body == b"{}" and _status(sent) == 200


def test_other_paths_and_methods_are_not_buffered():
    for scope in (_scope("/api/files", "POST"), _scope("/api/save", "GET")):
        downstream, _, _ = _run_middleware(scope, [{"type": "http.request", "body": b"zz"}])
        assert downstream.called and downstream.body == b"zz"


# --------------------------------------------------------------------------- #
# Origin, host, and peer policy edge cases
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "origin",
    ["http://[::1", "http://localhost:99999", "http://localhost:abc", "http://[zz]:80", "http://[::1]:-1"],
)
def test_malformed_origins_are_refused_not_crashing(origin, client):
    assert is_origin_allowed(origin, "localhost:8000") is False
    res = client.get("/api/health", headers={"origin": origin})
    assert res.status_code == 403


def test_malformed_origin_on_websocket_is_refused(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as info:
        with client.websocket_connect("/api/render", headers={"origin": "http://[::1"}) as ws:
            ws.receive_json()
    assert info.value.code == 1008


def test_policy_errors_are_403(client):
    with patch.object(main, "is_origin_allowed", side_effect=ValueError("boom")):
        assert client.get("/api/health").status_code == 403


def test_origin_port_defaults_and_header_ports(monkeypatch):
    monkeypatch.setenv("MANIM_DEV_ORIGIN_PORTS", "80, 443, junk")
    assert origins.dev_origin_ports() == {80, 443}
    assert is_origin_allowed("http://localhost", None) is True  # port 80 by scheme
    assert is_origin_allowed("https://localhost", None) is True  # port 443 by scheme
    monkeypatch.setenv("MANIM_DEV_ORIGIN_PORTS", "")
    assert is_origin_allowed("http://[::1]:8741", "[::1]:8741") is True
    assert is_origin_allowed("http://[::1]:8741", "[::1]") is False
    assert is_origin_allowed("http://localhost:8741", "localhost") is False
    assert origins._header_port("[::1]:8741") == 8741
    assert origins._header_port("[::1") is None
    assert origins._header_port("localhost:abc") is None
    assert origins._header_port("::1") is None
    assert origins._origin_port(origins.urlparse("ftp://localhost")) is None


def test_configured_origin_that_cannot_be_parsed_is_ignored(monkeypatch):
    monkeypatch.setenv("MANIM_ALLOWED_ORIGINS", "http://[broken, https://app.example")
    assert is_host_allowed("app.example") is True
    assert is_host_allowed("other.example") is False


@pytest.mark.parametrize("peer", [None, "", "testclient", "127.0.0.1", "127.8.0.1", "::1", "localhost"])
def test_loopback_peers_are_allowed(peer, monkeypatch):
    monkeypatch.delenv("MANIM_ALLOW_LAN", raising=False)
    monkeypatch.delenv("RUNNING_IN_DOCKER", raising=False)
    assert is_peer_allowed(peer) is True


def test_remote_peer_needs_lan_or_docker(monkeypatch):
    monkeypatch.delenv("MANIM_ALLOW_LAN", raising=False)
    monkeypatch.delenv("RUNNING_IN_DOCKER", raising=False)
    assert is_peer_allowed("192.168.1.20") is False
    monkeypatch.setenv("MANIM_ALLOW_LAN", "1")
    assert is_peer_allowed("192.168.1.20") is True
    monkeypatch.delenv("MANIM_ALLOW_LAN")
    monkeypatch.setenv("RUNNING_IN_DOCKER", "TRUE")
    assert is_peer_allowed("172.17.0.1") is True


def test_remote_peer_is_refused_by_the_middleware(monkeypatch):
    monkeypatch.delenv("MANIM_ALLOW_LAN", raising=False)
    monkeypatch.delenv("RUNNING_IN_DOCKER", raising=False)
    assert main._request_allowed({"host": "localhost:8000"}, "203.0.113.9") is False
    assert main._request_allowed({"host": "localhost:8000"}, "127.0.0.1") is True
    assert main._peer_host(None) is None


# --------------------------------------------------------------------------- #
# DELETE /api/media: resolve, then check the media folder
# --------------------------------------------------------------------------- #


@pytest.fixture
def media_tree(tmp_path):
    media = tmp_path / "media"
    keep_video = media / "videos" / "keep" / "480p15" / "Keep.mp4"
    keep_image = media / "images" / "keep" / "Keep.png"
    for path in (keep_video, keep_image):
        path.parent.mkdir(parents=True)
        path.write_text("x")
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)), patch.object(main, "MEDIA_DIR", str(media)):
        yield tmp_path, media, keep_video, keep_image


@pytest.mark.parametrize(
    "path",
    [
        "videos/x/../keep/480p15/Keep.mp4",
        "videos/../images/keep/Keep.png",
        "videos/a/../../images/keep/Keep.png",
        "videos/keep/480p15/../480p15/Keep.mp4",
        "videos\\..\\images\\keep\\Keep.png",
        "media/videos/keep/480p15/..\\480p15\\Keep.mp4",
        "videos/keep/480p15/Keep.mp4\x00.mp4",
        "videos/Keep.mp4/..",
        "videos",
        "videos/",
        "/",
        "",
    ],
)
def test_delete_media_refuses_parent_segments(client, media_tree, path):
    _, _, keep_video, keep_image = media_tree
    assert client.delete("/api/media", params={"path": path}).status_code == 400
    assert keep_video.exists() and keep_image.exists()


def test_delete_media_symlink_removes_only_the_link(client, media_tree, tmp_path):
    """A link planted under media/ is removed as a link; its target is never deleted."""
    _, media, keep_video, keep_image = media_tree
    outside = tmp_path / "outside.mp4"
    outside.write_text("x")
    for link, target in (
        (media / "videos" / "keep" / "480p15" / "Link.mp4", keep_image),
        (media / "images" / "keep" / "Out.png", outside),
    ):
        os.symlink(target, link)
        rel = link.relative_to(media).as_posix()
        assert client.delete("/api/media", params={"path": rel}).status_code in (200, 400)
    assert keep_image.exists() and outside.exists() and keep_video.exists()


def test_delete_media_accepts_the_media_prefix(client, media_tree):
    _, _, keep_video, _ = media_tree
    res = client.delete("/api/media", params={"path": "/media/videos/keep/480p15/Keep.mp4"})
    assert res.status_code == 200
    assert res.json()["path"] == "videos/keep/480p15/Keep.mp4"
    assert not keep_video.exists()


def test_delete_media_os_error_is_500(client, media_tree):
    with patch.object(main.os, "remove", side_effect=OSError("busy")):
        res = client.delete("/api/media", params={"path": "images/keep/Keep.png"})
    assert res.status_code == 500


# --------------------------------------------------------------------------- #
# Boolean flags on the render request
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, False), (False, False), (True, True), (0, False), (1, True),
        ("false", False), ("False", False), ("0", False), ("no", False), ("off", False), ("", False),
        ("true", True), (" TRUE ", True), ("1", True), ("yes", True), ("on", True),
    ],
)
def test_flags_are_coerced(value, expected):
    message = {"filename": "a.py", "scene": "A", "use_opengl": value, "download_only": value}
    request = main._validate_start_message(message)
    assert request["use_opengl"] is expected
    assert request["download_only"] is expected


@pytest.mark.parametrize("value", ["maybe", 2, -1, 0.5, [1], {"a": 1}])
def test_invalid_flags_are_rejected(value):
    with pytest.raises(main._RenderRequestError, match="use_opengl"):
        main._validate_start_message({"filename": "a.py", "scene": "A", "use_opengl": value})


def test_invalid_flag_over_the_socket_gets_a_rejected_result(client):
    with client.websocket_connect("/api/render") as ws:
        ws.send_json({"type": "start", "id": "f", "filename": "a.py", "scene": "A", "use_opengl": "maybe"})
        error, result = ws.receive_json(), ws.receive_json()
    assert error["render_id"] == "f" and "use_opengl" in error["message"]
    assert result == {"type": "result", "render_id": "f", "success": False, "status": "rejected"}


# --------------------------------------------------------------------------- #
# Startup maintenance runs from the lifespan hook only
# --------------------------------------------------------------------------- #


def test_lifespan_sweeps_only_after_the_port_is_bound(monkeypatch):
    calls = []
    listening = {"now": False}
    monkeypatch.setattr(main, "RUN_STARTUP_MAINTENANCE", True)
    monkeypatch.setattr(main, "_sweep_temp_renders", lambda: calls.append("sweep"))
    monkeypatch.setattr(main, "write_manim_config_file", lambda *a: calls.append("cfg"))
    monkeypatch.setattr(main, "get_cached_profile", lambda: {})
    monkeypatch.setattr(main, "_process_is_listening", lambda: listening["now"])

    async def run():
        async with main._lifespan(main.app):
            calls.append("running")
            await asyncio.sleep(0.15)
            assert "sweep" not in calls  # not bound yet: nothing is touched
            listening["now"] = True
            for _ in range(50):
                if "sweep" in calls:
                    break
                await asyncio.sleep(0.02)

    asyncio.run(run())
    assert calls == ["cfg", "running", "sweep"]


def test_server_that_never_binds_never_sweeps(monkeypatch):
    """uvicorn runs the lifespan before bind(); "address in use" exits without sweeping."""
    calls = []
    monkeypatch.setattr(main, "_sweep_temp_renders", lambda: calls.append("sweep"))
    monkeypatch.setattr(main, "_process_is_listening", lambda: False)
    assert asyncio.run(main._maintenance_after_bind(wait_seconds=0.1, poll=0.02)) is False
    assert calls == []


def test_lifespan_shutdown_cancels_a_pending_sweep(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "RUN_STARTUP_MAINTENANCE", True)
    monkeypatch.setattr(main, "_sweep_temp_renders", lambda: calls.append("sweep"))
    monkeypatch.setattr(main, "write_manim_config_file", lambda *a: None)
    monkeypatch.setattr(main, "get_cached_profile", lambda: {})
    monkeypatch.setattr(main, "_process_is_listening", lambda: False)

    async def run():
        async with main._lifespan(main.app):
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.2)

    asyncio.run(run())
    assert calls == []


def test_process_is_listening_sees_a_bound_socket():
    import socket

    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        assert main._process_is_listening() is True


def test_sweep_ignores_unreadable_workspace(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "WORKSPACE_DIR", str(tmp_path / "missing"))
    monkeypatch.setattr(main, "MEDIA_DIR", str(tmp_path / "missing" / "media"))
    main._sweep_temp_renders()  # must not raise


def test_oversized_json_with_content_length_is_413(client):
    body = json.dumps({"code": "#" * (main.MAX_CODE_BYTES + 1)})
    assert client.post("/api/parse-code", content=body, headers={"content-type": "application/json"}).status_code == 413
