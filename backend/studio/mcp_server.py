"""Agent tools for the same Studio service used by the app.

HTTP: mounted by main.py at /mcp (explicit bearer credential required).
stdio: ``python backend/studio/mcp_server.py --url http://127.0.0.1:8000``
bridges to the running app, so it never starts a second render queue.
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import sys
from contextlib import asynccontextmanager
from typing import Literal
from urllib.parse import quote, urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.mcpserver import Context, Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import TextContent

from studio.errors import StudioError
from studio.registry import TemplateError
from studio.schema import RenderSettings
from studio.themes import THEMES


def _tool_errors(fn):
    @functools.wraps(fn)
    async def wrapped(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except TemplateError as exc:
            raise ToolError(json.dumps({"detail": str(exc), "errors": exc.errors})) from None
        except StudioError as exc:
            raise ToolError(str(exc)) from None
    return wrapped


def settings_schema(template: dict) -> dict:
    """JSON Schema of the shared render settings, narrowed to what *template* accepts."""
    schema = RenderSettings.model_json_schema()
    props = schema["properties"]
    props["theme"]["enum"] = list(THEMES)
    props["theme"]["description"] = "; ".join(f"{tid}: {t['name']}" for tid, t in THEMES.items())
    props["aspect"] = {**props["aspect"], "enum": template["aspects"], "default": template["default_aspect"]}
    if template.get("length_from_params"):
        props["length"]["description"] = "Ignored: this template's content sets the length."
    else:
        props["length"]["description"] = (f"Seconds, {template['min_length']:g}-{template['max_length']:g}; "
                                          f"omit for the default {template['default_length']:g}.")
    return schema


def create_server(service, *, base_url: str = "http://127.0.0.1:8000") -> MCPServer:
    """Build tools without importing Manim. A service may also be a REST bridge."""
    server = MCPServer(
        "Composer Studio", version="1.1.0",
        instructions=("Make animated clips from installed templates. Search, then get_template for the exact params schema, "
                      "settings_schema and presets. Create a project, preview its storyboard, revise, then export. Do not "
                      "invent fields. For photos and logos call add_image and use the returned name. "
                      "update_project replaces params/settings when supplied; get_project first to preserve other fields. "
                      "Exports are background jobs: call get_export until done, then return its URL. No Python code is accepted."))

    def origin(ctx):
        try:
            host = (ctx.headers or {}).get("host")
        except (ValueError, LookupError):
            host = None
        # HTTP host already passed the app's origin/host policy. stdio uses --url.
        return f"http://{host}" if host else base_url

    @server.tool()
    @_tool_errors
    async def search_templates(query: str = "", category: str = "") -> list[dict]:
        """Find templates and ready-to-use presets by everyday task: sale, birthday, timer, quiz, quote, year review."""
        catalog = await service.catalog()
        words = query.casefold().split()
        return [{"id": t["id"], "title": t["title"], "summary": t["summary"], "when_to_use": t["when_to_use"],
                 "presets": t["presets"], "aspects": t["aspects"]}
                for t in catalog["templates"] if (not category or category == t["category"])
                and all(word in json.dumps({k: t.get(k) for k in ("id", "title", "summary", "tags", "presets")},
                                           ensure_ascii=False).casefold() for word in words)]

    @server.tool()
    @_tool_errors
    async def get_template(template: str) -> dict:
        """Return the template's params JSON Schema, settings_schema (theme, aspect, background, brand...),
        defaults, presets and timing limits."""
        info = await service.template_info(template)
        return {**info, "settings_schema": settings_schema(info)}

    @server.tool()
    @_tool_errors
    async def create_project(template: str, ctx: Context, params: dict | None = None, settings: dict | None = None,
                             title: str | None = None) -> dict:
        """Save a project visible in the app. Copy a preset's params/settings or follow get_template's schema."""
        result = await service.create_project(template, params, settings, title)
        return {**result, "app_url": f"{origin(ctx)}/#/project/{result['id']}"}

    @server.tool()
    @_tool_errors
    async def list_projects() -> list[dict]:
        """List saved projects, newest first."""
        return await service.list_projects()

    @server.tool()
    @_tool_errors
    async def get_project(project_id: str) -> dict:
        """Read a project's full params and settings before revising it."""
        return await service.get_project(project_id)

    @server.tool()
    @_tool_errors
    async def update_project(project_id: str, params: dict | None = None, settings: dict | None = None,
                             title: str | None = None) -> dict:
        """Replace the supplied fields; omitted fields stay unchanged. Params/settings replace the whole object."""
        fields = {k: v for k, v in {"params": params, "settings": settings, "title": title}.items() if v is not None}
        return await service.update_project(project_id, **fields)

    @server.tool(structured_output=False)
    @_tool_errors
    async def preview(project_id: str, mode: Literal["poster", "storyboard", "motion"] = "storyboard") -> list:
        """Inspect a poster/storyboard, or queue a silent motion preview (first 20s). Poll get_motion for its video URL."""
        project = await service.get_project(project_id)
        if mode == "motion":
            result = await service.start_motion(project_id, project["template"], project["params"], project["settings"])
            return [TextContent(type="text", text=json.dumps(result))]
        result = await service.preview(project["template"], project["params"], project["settings"], mode)
        if "path" in result:
            image = Image(path=result.pop("path"))
        else:
            image = Image(data=await service.image_bytes(result["url"]), format="png")
        return [TextContent(type="text", text=json.dumps(result)), image.to_image_content()]

    @server.tool()
    @_tool_errors
    async def get_motion(preview_id: str) -> dict:
        """Get a motion preview's status and video URL when done."""
        return await service.get_motion(preview_id)

    @server.tool()
    @_tool_errors
    async def cancel_motion(preview_id: str) -> dict:
        """Stop a queued or running motion preview."""
        return await service.cancel_motion(preview_id)

    @server.tool(name="export_project")
    @_tool_errors
    async def export_project(project_id: str, format: Literal["mp4", "png", "gif", "webm", "mov"] = "mp4",
                             quality: Literal["draft", "720p", "1080p", "1080p60", "4k"] = "1080p") -> dict:
        """Queue a saved project for export. Return immediately with a job id; poll get_export. PNG is a still."""
        project = await service.get_project(project_id)
        return await service.start_export(project["template"], project["params"], project["settings"],
                                          format=format, quality=quality, title=project["title"])

    @server.tool()
    @_tool_errors
    async def get_export(export_id: str, ctx: Context) -> dict:
        """Read a job's status and progress. When done, download_url points to the finished file."""
        result = await service.get_export(export_id)
        if result.get("url"):
            result["download_url"] = origin(ctx) + result["url"]
        return result

    @server.tool()
    @_tool_errors
    async def cancel_export(export_id: str) -> dict:
        """Cancel a queued or running export."""
        return await service.cancel_export(export_id)

    @server.tool()
    @_tool_errors
    async def add_image(data_base64: str) -> dict:
        """Add a photo or logo (PNG, JPEG, GIF, WebP or SVG as base64, at most 8 MB). Put the returned name in
        a template's image field (photo, avatar, image, logo). The same picture always gets the same name."""
        return await service.add_image(data_base64)

    @server.tool()
    @_tool_errors
    async def list_icons() -> list[str]:
        """List the bundled icon names accepted by template icon fields."""
        return await service.icon_names()

    return server


class RestBridge:
    """One stdio client proxies the running app, sharing its cache, projects and export queue."""
    def __init__(self, client):
        self.client = client

    async def request(self, method, path, **kwargs):
        import httpx2 as httpx

        try:
            response = await self.client.request(method, "/api/studio" + path, **kwargs)
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ToolError(f"Could not reach Composer Studio. Open the app and check --url ({type(exc).__name__}).") from None
        if response.is_error:
            raise ToolError(json.dumps(data))
        return data

    async def catalog(self):
        return await self.request("GET", "/catalog")

    async def template_info(self, template):
        return await self.request("GET", "/templates/" + quote(template, safe=""))

    async def list_projects(self):
        return await self.request("GET", "/projects")

    async def create_project(self, template, params, settings, title):
        return await self.request("POST", "/projects", json={"template": template, "params": params, "settings": settings, "title": title})

    async def get_project(self, project_id):
        return await self.request("GET", "/projects/" + quote(project_id, safe=""))

    async def update_project(self, project_id, **fields):
        return await self.request("PUT", "/projects/" + quote(project_id, safe=""), json=fields)

    async def preview(self, template, params, settings, mode):
        return await self.request("POST", "/preview", json={"template": template, "params": params, "settings": settings, "mode": mode})

    async def start_motion(self, project, template, params, settings):
        return await self.request("POST", "/motion", json={"project": project, "template": template,
                                   "params": params, "settings": settings})

    async def get_motion(self, preview_id):
        return await self.request("GET", "/motion/" + quote(preview_id, safe=""))

    async def cancel_motion(self, preview_id):
        return await self.request("DELETE", "/motion/" + quote(preview_id, safe=""))

    async def image_bytes(self, url):
        if not url.startswith("/media/studio/previews/") or ".." in url:
            raise ToolError("The app returned an invalid preview URL.")
        response = await self.client.get(url)
        if response.is_error:
            raise ToolError("The preview image could not be loaded.")
        return response.content

    async def start_export(self, template, params, settings, **fields):
        return await self.request("POST", "/exports", json={"template": template, "params": params, "settings": settings, **fields})

    async def get_export(self, export_id):
        return await self.request("GET", "/exports/" + quote(export_id, safe=""))

    async def cancel_export(self, export_id):
        return await self.request("DELETE", "/exports/" + quote(export_id, safe=""))

    async def add_image(self, data):
        return await self.request("POST", "/images", json={"data": data})

    async def icon_names(self):
        return await self.request("GET", "/icons")


def main():
    import asyncio
    import httpx2 as httpx

    parser = argparse.ArgumentParser(description="Connect an MCP client to the running Composer Studio app over stdio.")
    parser.add_argument("--url", default=os.environ.get("COMPOSER_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--token-file", help="Read the app's workspace/studio/mcp-token (or set COMPOSER_TOKEN).")
    args = parser.parse_args()
    url = urlsplit(args.url)
    if url.scheme != "http" or url.hostname not in ("localhost", "127.0.0.1", "::1") or url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
        parser.error("--url must name the local app, e.g. http://127.0.0.1:8000")
    token = os.environ.get("COMPOSER_TOKEN", "")
    if args.token_file:
        with open(args.token_file, encoding="ascii") as f:
            token = f.read().strip()
    if not token:
        parser.error("Set COMPOSER_TOKEN or pass --token-file from the app's workspace/studio folder.")

    @asynccontextmanager
    async def client_context():
        async with httpx.AsyncClient(base_url=args.url.rstrip("/"), timeout=90,
                                     headers={"Authorization": f"Bearer {token}"}, trust_env=False) as client:
            yield client

    async def run():
        async with client_context() as client:
            await create_server(RestBridge(client), base_url=args.url.rstrip("/")).run_stdio_async()
    asyncio.run(run())


if __name__ == "__main__":
    main()
