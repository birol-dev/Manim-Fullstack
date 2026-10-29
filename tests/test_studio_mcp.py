"""Agent edits, image feedback and exports use the app's service and validation."""

import asyncio
import json
import os

import pytest

pytest.importorskip("mcp.server.mcpserver")

from studio.mcp_server import RestBridge, create_server
from mcp.server.mcpserver.exceptions import ToolError
from tests.studio_fakes import make_service
from tests.studio_fakes import FakeMotionWorker, FakeRunner, RunnerFactory, wait_until


def run(coro):
    return asyncio.run(coro)


def payload(result):
    assert not result.is_error, result
    return json.loads(next(c.text for c in result.content if c.type == "text"))


def listing(result):
    """A tool that returns a list answers one text block per item."""
    assert not result.is_error, result
    return [json.loads(c.text) for c in result.content if c.type == "text"]


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


def test_agent_export_history_remove_and_retry(tmp_path):
    service, _ = make_service(tmp_path)
    server = create_server(service)
    try:
        names = {tool.name for tool in run(server.list_tools())}
        assert {"list_exports", "remove_export", "retry_export", "delete_project", "duplicate_project"} <= names
        project = payload(run(server.call_tool("create_project", {"template": "countdown", "params": {"seconds": 4},
                                                                 "title": "Timer"})))
        first = payload(run(server.call_tool("export_project", {"project_id": project["id"], "quality": "draft"})))
        second = payload(run(server.call_tool("export_project", {"project_id": project["id"], "quality": "draft"})))

        def finished(export_id):
            return wait_until(lambda: (record if (record := payload(run(server.call_tool(
                "get_export", {"export_id": export_id}))))["status"] == "done" else None))

        done = {record["id"]: finished(record["id"]) for record in (first, second)}
        listed = listing(run(server.call_tool("list_exports", {})))
        assert [record["id"] for record in listed] == [second["id"], first["id"]]  # newest first
        assert listed[0]["download_url"] == "http://127.0.0.1:8000" + done[second["id"]]["url"]
        assert listed[1]["download_url"] == "http://127.0.0.1:8000" + done[first["id"]]["url"]

        again = payload(run(server.call_tool("retry_export", {"export_id": first["id"]})))
        assert again["id"] not in (first["id"], second["id"]) and again["status"] == "queued"
        assert run(service.get_export(again["id"]))["request"] == done[first["id"]]["request"]

        kept = payload(run(server.call_tool("remove_export", {"export_id": first["id"], "delete_file": False})))
        assert os.path.isfile(os.path.join(service.exports_dir, kept["filename"]))  # the file stays
        assert first["id"] not in [record["id"] for record in listing(run(server.call_tool("list_exports", {})))]
        deleted = payload(run(server.call_tool("remove_export", {"export_id": second["id"]})))
        assert not os.path.exists(os.path.join(service.exports_dir, deleted["filename"]))
        assert second["id"] not in [record["id"] for record in listing(run(server.call_tool("list_exports", {})))]
    finally:
        service.shutdown_sync()


def test_agent_remove_a_running_export_conflicts(tmp_path):
    blocker = FakeRunner("block")
    service, _ = make_service(tmp_path, runners=RunnerFactory(blocker))
    server = create_server(service)
    try:
        project = payload(run(server.call_tool("create_project", {"template": "countdown"})))
        job = payload(run(server.call_tool("export_project", {"project_id": project["id"], "quality": "draft"})))
        assert blocker.started.wait(5)
        with pytest.raises(ToolError, match="cancel it first"):
            run(server.call_tool("remove_export", {"export_id": job["id"]}))
        assert payload(run(server.call_tool("cancel_export", {"export_id": job["id"]})))["status"] == "cancelled"
        assert payload(run(server.call_tool("remove_export", {"export_id": job["id"]})))["id"] == job["id"]
    finally:
        service.shutdown_sync()


def test_agent_retry_needs_a_stored_request(tmp_path):
    service, _ = make_service(tmp_path)
    server = create_server(service)
    try:
        manager = service._export_manager()
        manager._ensure_loaded()
        with manager._lock:
            manager._records["abcdef000001"] = {"id": "abcdef000001", "status": "failed", "created": "1"}
        with pytest.raises(ToolError, match="no stored request"):
            run(server.call_tool("retry_export", {"export_id": "abcdef000001"}))
        with pytest.raises(ToolError, match="No export"):
            run(server.call_tool("retry_export", {"export_id": "000000000000"}))
    finally:
        service.shutdown_sync()


def test_agent_duplicates_and_deletes_projects(tmp_path):
    service, _ = make_service(tmp_path)
    server = create_server(service)
    try:
        project = payload(run(server.call_tool("create_project", {"template": "countdown", "params": {"seconds": 5},
                                                                 "title": "Class break"})))
        copy = payload(run(server.call_tool("duplicate_project", {"project_id": project["id"]})))
        assert copy["id"] != project["id"] and copy["title"] == "Class break copy"
        assert copy["template"] == "countdown" and copy["params"] == {"seconds": 5}
        named = payload(run(server.call_tool("duplicate_project", {"project_id": project["id"], "title": "Second"})))
        assert named["title"] == "Second"
        assert payload(run(server.call_tool("delete_project", {"project_id": project["id"]})))["id"] == project["id"]
        with pytest.raises(ToolError, match="No project"):
            run(server.call_tool("get_project", {"project_id": project["id"]}))
        assert {p["id"] for p in listing(run(server.call_tool("list_projects", {})))} == {copy["id"], named["id"]}
    finally:
        service.shutdown_sync()


def test_stdio_bridge_manages_exports_and_projects(tmp_path):
    import httpx
    from fastapi import FastAPI
    from studio import api

    service, _ = make_service(tmp_path)
    app = FastAPI()
    app.include_router(api.router)
    original = api.service_module.service
    api.service_module.service = service

    async def settled(bridge, export_id):
        for _ in range(500):
            record = await bridge.get_export(export_id)
            if record["status"] in ("done", "failed", "cancelled"):
                return record
            await asyncio.sleep(0.02)
        raise AssertionError("export did not finish")

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
            bridge = RestBridge(client)
            project = await bridge.create_project("countdown", {"seconds": 4}, {}, "Bridge copy")
            copy = await bridge.duplicate_project(project["id"])
            assert copy["title"] == "Bridge copy copy" and copy["id"] != project["id"]
            first = await bridge.start_export("countdown", {"seconds": 4}, {}, format="mp4", quality="draft",
                                              title="Bridge export")
            done = await settled(bridge, first["id"])
            listed = await bridge.list_exports()
            assert [record["id"] for record in listed] == [first["id"]] and listed[0]["url"] == done["url"]
            again = await bridge.retry_export(first["id"])
            assert again["id"] != first["id"] and again["template"] == "countdown"
            await settled(bridge, again["id"])
            kept = await bridge.remove_export(first["id"], delete_file=False)
            assert os.path.isfile(os.path.join(service.exports_dir, kept["filename"]))
            assert [record["id"] for record in await bridge.list_exports()] == [again["id"]]
            deleted = await bridge.remove_export(again["id"])
            assert not os.path.exists(os.path.join(service.exports_dir, deleted["filename"]))
            assert await bridge.list_exports() == []
            await bridge.delete_project(copy["id"])
            with pytest.raises(ToolError, match="No project"):
                await bridge.get_project(copy["id"])
    try:
        run(scenario())
    finally:
        api.service_module.service = original
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
