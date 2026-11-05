"""Author tools share editor files and render results behind a workspace opt-in."""

import json
import time

import pytest

import main
from studio.author_mcp import RenderJobs


AGENT = {"Authorization": "Bearer agent-test-key"}
DESKTOP = {"Authorization": "Bearer desktop-test-key"}
SETTING = "/api/author/ai-python"
ACTIVITY = "/api/author/activity"
SCRIPT = "from manim import Scene\n\nclass Demo(Scene):\n    def construct(self):\n        self.wait(1)\n"


@pytest.fixture
def author_client(client, workspace, monkeypatch):
    pytest.importorskip("mcp.server.mcpserver")
    monkeypatch.setattr(main, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setattr(main, "MEDIA_DIR", str(workspace / "media"))
    monkeypatch.setattr(main, "author_renders", RenderJobs())
    monkeypatch.setattr(main, "_render_slots", None)
    monkeypatch.setenv("MANIM_API_TOKEN", "desktop-test-key")
    monkeypatch.setenv("MANIM_MCP_TOKEN", "agent-test-key")
    with client:
        yield client


def call(client, name, **arguments):
    response = client.post("http://localhost:8000/mcp/", headers={**AGENT, "Accept": "application/json, text/event-stream"}, json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments},
    })
    assert response.status_code == 200, response.text
    if response.headers["content-type"].startswith("text/event-stream"):
        message = next(json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: "))
    else:
        message = response.json()
    result = message["result"]
    text = result["content"][0]["text"]
    return text if result.get("isError") else json.loads(text)


def test_only_app_can_enable_python_and_edits_use_author_file_versions(author_client, workspace):
    client = author_client
    assert "Enable Python authoring" in call(client, "list_scripts")
    assert client.get(ACTIVITY, headers=AGENT).status_code == 401
    assert client.get(ACTIVITY, headers=DESKTOP).json() == {"enabled": False, "items": []}
    assert client.put(SETTING, json={"enabled": True}, headers=AGENT).status_code == 401
    assert client.put(SETTING, json={"enabled": True}, headers=DESKTOP).json() == {"enabled": True}

    assert isinstance(call(client, "write_script", filename="../demo.py", code=SCRIPT), str)
    assert not (workspace / "demo.py").exists()
    saved = call(client, "write_script", filename="demo.py", code=SCRIPT)
    assert saved["scenes"] == ["Demo"]
    activity = client.get(ACTIVITY, headers=DESKTOP).json()
    assert activity["enabled"] and len(activity["items"]) == 1
    assert activity["items"][0]["filename"] == "demo.py"
    assert activity["items"][0]["kind"] == "script"
    assert activity["items"][0]["version"] == saved["version"]
    assert [script["name"] for script in call(client, "list_scripts")["scripts"]] == ["demo.py"]
    author_file = client.get("/api/file-content", params={"filename": "demo.py"}, headers=DESKTOP).json()
    assert (author_file["code"], author_file["version"]) == (SCRIPT, saved["version"])
    assert "already exists" in call(client, "write_script", filename="demo.py", code="")
    assert "changed outside" in call(client, "write_script", filename="demo.py", code="", base_version="old")
    bridge = client.post("/api/studio/author/read_script", headers=AGENT, json={"filename": "demo.py"})
    assert bridge.json() == author_file == call(client, "read_script", filename="demo.py")

    assert client.put(SETTING, json={"enabled": False}, headers=DESKTOP).json() == {"enabled": False}
    assert "Enable Python authoring" in call(client, "read_script", filename="demo.py")


def test_python_render_reuses_editor_pipeline_and_reports_media(author_client, workspace, monkeypatch):
    client = author_client
    monkeypatch.setattr(main, "get_binary_paths", lambda: {"manim_command": ["manim"]})

    class Executor:
        def __init__(self, *_args, **_kwargs):
            pass

        async def execute(self, script_name, scene_name, log_callback, **_kwargs):
            assert (workspace / script_name).read_text(encoding="utf-8") == SCRIPT
            await log_callback({"type": "progress", "percent": 50})
            await log_callback({"type": "log", "message": "Rendering Demo"})
            path = workspace / "media" / "videos" / "demo" / f"{scene_name}.mp4"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"movie")
            await log_callback({"type": "file_ready", "abs_path": str(path), "rel_path": "media/videos/demo/Demo.mp4"})
            return {"success": True, "status": "success"}

    monkeypatch.setattr(main, "ManimExecutor", Executor)
    assert client.put(SETTING, json={"enabled": True}, headers=DESKTOP).status_code == 200
    saved = call(client, "write_script", filename="demo.py", code=SCRIPT)
    assert "changed" in call(client, "render_scene", filename="demo.py", scene="Demo", version="old")
    job = call(client, "render_scene", filename="demo.py", scene="Demo", version=saved["version"])
    deadline = time.monotonic() + 5
    while job["status"] in ("queued", "rendering") and time.monotonic() < deadline:
        job = call(client, "get_scene_render", render_id=job["id"])
        time.sleep(0.01)
    assert job["status"] == "done", job
    assert job["logs"] == ["Rendering Demo"]
    assert job["output"]["url"] == "/media/videos/demo/Demo.mp4"
    assert job["app_url"].endswith("/#/author")
    assert job["design_url"].endswith("/#/author/design?file=demo.py&scene=Demo")
    render = client.get(ACTIVITY, headers=DESKTOP).json()["items"][0]
    assert render["id"] == job["id"] and render["kind"] == "render" and render["status"] == "done"
    assert render["output"] == job["output"] and "logs" not in render
