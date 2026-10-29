"""Agent edits, image feedback and exports use the app's service and validation."""

import asyncio
import json

import pytest

pytest.importorskip("mcp.server.mcpserver")

from studio.mcp_server import RestBridge, create_server
from mcp.server.mcpserver.exceptions import ToolError
from tests.studio_fakes import make_service
from tests.studio_fakes import FakeMotionWorker, wait_until


def run(coro):
    return asyncio.run(coro)


def payload(result):
    assert not result.is_error, result
    return json.loads(next(c.text for c in result.content if c.type == "text"))


def test_agent_motion_preview(tmp_path):
    service, _ = make_service(tmp_path, motion_worker_factory=FakeMotionWorker)
    server = create_server(service)
    try:
        project = run(service.create_project("countdown"))
        job = payload(run(server.call_tool("preview", {"project_id": project["id"], "mode": "motion"})))
        done = wait_until(lambda: (record if (record := payload(run(server.call_tool("get_motion", {"preview_id": job["id"]}))))["status"] == "done" else None))
        assert done["url"].endswith(".mp4") and done["truncated"]
        assert payload(run(server.call_tool("cancel_motion", {"preview_id": job["id"]})))["status"] == "done"
    finally:
        service.shutdown_sync()


def test_agent_project_preview_and_export(tmp_path):
    service, worker = make_service(tmp_path)
    server = create_server(service)
    try:
        names = {tool.name for tool in run(server.list_tools())}
        assert {"search_templates", "get_template", "create_project", "update_project", "preview", "export_project", "get_export"} <= names
        assert "render_code" not in names
        info = payload(run(server.call_tool("get_template", {"template": "countdown"})))
        assert info["schema"]["properties"]["seconds"]["minimum"] >= 1
        settings = info["settings_schema"]["properties"]
        assert "pop" in settings["theme"]["enum"] and settings["aspect"]["enum"] == info["aspects"]
        assert {"background", "brand", "energy", "ending", "safe_zone", "locale"} <= set(settings)
        project = payload(run(server.call_tool("create_project", {"template": "countdown", "params": {"seconds": 5}, "title": "Class break"})))
        pid = project["id"]
        assert run(service.get_project(pid))["title"] == "Class break"
        payload(run(server.call_tool("update_project", {"project_id": pid, "title": "Updated by agent"})))
        assert run(service.get_project(pid))["params"] == {"seconds": 5}
        result = run(server.call_tool("preview", {"project_id": pid}))
        assert not result.is_error, result
        assert any(c.type == "image" and c.mime_type == "image/png" for c in result.content)
        assert worker.calls[-1]["job"]["mode"] == "storyboard"
        import base64
        from tests.studio_fakes import tiny_png
        image = payload(run(server.call_tool("add_image", {"data_base64": base64.b64encode(tiny_png(2, 2)).decode()})))
        assert image["name"].startswith("agent-") and image["name"].endswith(".png")
        export = payload(run(server.call_tool("export_project", {"project_id": pid, "quality": "draft"})))
        assert export["template"] == "countdown" and export["id"]
        assert run(service.list_exports())[0]["id"] == export["id"]
    finally:
        service.shutdown_sync()


def test_agent_field_errors_are_actionable(tmp_path):
    service, _ = make_service(tmp_path)
    server = create_server(service)
    try:
        with pytest.raises(ToolError, match="Unknown template"):
            run(server.call_tool("get_template", {"template": "../../outside"}))
        # Draft projects may save invalid fields while typing. Rendering validates them.
        project = payload(run(server.call_tool("create_project", {"template": "countdown", "params": {"seconds": -2}})))
        with pytest.raises(ToolError, match="params.seconds"):
            run(server.call_tool("preview", {"project_id": project["id"]}))
    finally:
        service.shutdown_sync()


def test_agent_quiz_choices_keep_1_based_validation(tmp_path):
    service, _ = make_service(tmp_path)
    server = create_server(service)
    try:
        info = payload(run(server.call_tool("get_template", {"template": "quiz"})))
        correct = info["schema"]["properties"]["correct"]
        assert correct["x-choice-of"] == "options" and correct["type"] == "integer"
        project = payload(run(server.call_tool("create_project", {"template": "quiz", "params": {"options": ["Yes", "No"], "correct": 2}})))
        result = run(server.call_tool("preview", {"project_id": project["id"]}))
        assert not result.is_error
        payload(run(server.call_tool("update_project", {"project_id": project["id"], "params": {"options": ["Yes", "No"], "correct": 3}})))
        with pytest.raises(ToolError, match="params.correct"):
            run(server.call_tool("preview", {"project_id": project["id"]}))
    finally:
        service.shutdown_sync()


def test_stdio_bridge_shares_app_state(tmp_path):
    import httpx
    from fastapi import FastAPI
    from studio import api

    service, worker = make_service(tmp_path)
    app = FastAPI()
    app.include_router(api.router)
    original = api.service_module.service
    api.service_module.service = service

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
            bridge = RestBridge(client)
            project = await bridge.create_project("countdown", {"seconds": 7}, {}, "Bridge")
            assert (await service.get_project(project["id"]))["title"] == "Bridge"
            await bridge.update_project(project["id"], title="Changed")
            assert (await service.get_project(project["id"]))["title"] == "Changed"
            await bridge.preview("countdown", {"seconds": 7}, {}, "poster")
            assert len(worker.calls) == 1
    try:
        run(scenario())
    finally:
        api.service_module.service = original
        service.shutdown_sync()
