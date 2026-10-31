"""Agent tools for the same Studio service used by the app.

HTTP: mounted by main.py at /mcp (explicit bearer credential required).
stdio: ``python backend/studio/mcp_server.py --url http://127.0.0.1:8000``
bridges to the running app, so it never starts a second render queue.
``--desktop-data <folder>`` (the desktop app's setup) uses the app when it is open
and otherwise starts its backend in the background (desktop/agent_host.py).
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
from studio.mcp_guide import register_guidance
from studio.registry import TemplateError
from studio.schema import RenderSettings
from studio.themes import THEMES
from studio.version import APP_VERSION


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
        "Manim Studio", version=APP_VERSION,
        instructions=(
            "Manim Studio makes short animated videos from installed templates. Call guide() first if "
            "unsure: it teaches the workflow, writing, platforms, look, sound and export.\n"
            "Workflow: search_templates -> get_template (exact params schema and presets) -> quick_video or "
            "create_project -> preview(mode=\"storyboard\") and look at the image -> update_project -> "
            "export_project -> poll get_export until done, then give the person download_url and the project id.\n"
            "Rules: never invent fields; keep text inside its maxLength (the layout is tested against them); "
            "get_project before update_project, because params and settings replace the whole object; images "
            "must be uploaded with add_image first; exports are background jobs, never assume one is done.\n"
            "Pick the aspect for the platform: 16:9 for YouTube and slides, 9:16 with safe_zone=true for "
            "Shorts/Reels/TikTok, 4:5 or 1:1 for Instagram feed. No Python code is accepted."))

    def origin(ctx):
        try:
            host = (ctx.headers or {}).get("host")
        except (ValueError, LookupError):
            host = None
        # HTTP host already passed the app's origin/host policy. stdio uses --url.
        return f"http://{host}" if host else base_url

    register_guidance(server, service)

    @server.tool()
    @_tool_errors
    async def search_templates(query: str = "", category: str = "") -> list[dict]:
        """Find templates and presets by the everyday job: sale, birthday, timer, quiz, quote, year
        review. Start here when you don't know an id. Matches id, title, summary, tags and preset
        text; category filters a gallery section. Returns id, title, summary, when_to_use, presets
        and aspects (not the params schema: call get_template for that)."""
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
        """Everything needed before creating a project: params JSON Schema (types, enums, maxLength,
        min/max items), settings_schema (theme, aspect, background, brand logo/colours/bundled font,
        sound), defaults, presets and timing limits. Call it instead of guessing a field: unknown
        fields are refused."""
        info = await service.template_info(template)
        return {**info, "settings_schema": settings_schema(info)}

    @server.tool()
    @_tool_errors
    async def create_project(template: str, ctx: Context, params: dict | None = None, settings: dict | None = None,
                             title: str | None = None) -> dict:
        """Save a project visible in the app and return it, including id and poster_url. Start from a
        preset's params/settings (get_template) or quick_video. Drafts may save incomplete input:
        preview and export validate it, so a bad field is reported then, with its path."""
        result = await service.create_project(template, params, settings, title)
        return {**result, "app_url": f"{origin(ctx)}/#/project/{result['id']}"}

    @server.tool(structured_output=False)
    @_tool_errors
    async def quick_video(template: str, ctx: Context, preset: str = "", params: dict | None = None,
                          settings: dict | None = None, title: str = "") -> list:
        """The fastest start: create a project from a preset (or the template's defaults) merged with
        your params/settings overrides, and return {project_id, project, storyboard, preview, app_url}
        together with the storyboard image. Look at that image, then update, preview or export.
        Use an unknown preset name and the error lists the valid ones."""
        info = await service.template_info(template)
        cards = {card["id"]: card for card in info.get("presets") or []}
        if preset and preset not in cards:
            raise ToolError(f"Unknown preset {preset!r} for {template}; use one of: "
                            + (", ".join(cards) or "none (this template has no presets)") + ".")
        card = cards.get(preset) or {}
        merged_params = {**(info.get("defaults") or {}), **(card.get("params") or {}), **(params or {})}
        merged_settings = {**(card.get("settings") or {}), **(settings or {})}
        project = await service.create_project(template, merged_params, merged_settings,
                                               title or card.get("title") or None)
        try:
            storyboard = await service.preview(project["template"], project["params"], project["settings"],
                                               "storyboard")
        except (StudioError, TemplateError, ToolError) as exc:
            # The project is saved: name it, so the next step fixes it instead of making a duplicate.
            detail = json.dumps({"detail": str(exc), "errors": exc.errors}) if isinstance(exc, TemplateError) else str(exc)
            raise ToolError(f"Saved project {project['id']} but its storyboard failed: {detail}. "
                            f"Fix it with get_project + update_project (do not call quick_video again), "
                            f"then preview it.") from None
        path = storyboard.pop("path", None)
        image = Image(path=path) if path else Image(data=await service.image_bytes(storyboard["url"]),
                                                    format="png")
        payload = {"project_id": project["id"], "project": project, "storyboard": storyboard.get("storyboard"),
                   "preview": storyboard, "app_url": f"{origin(ctx)}/#/project/{project['id']}"}
        return [TextContent(type="text", text=json.dumps(payload)), image.to_image_content()]

    @server.tool()
    @_tool_errors
    async def list_projects() -> list[dict]:
        """Saved projects, most recently updated first. Returns id, title, template, created, updated
        and poster_url. Use it to find a project id the person mentions by name."""
        return await service.list_projects()

    @server.tool()
    @_tool_errors
    async def get_project(project_id: str) -> dict:
        """A project's full template, params, settings, title, timestamps and poster_url. Always call
        this before update_project: params and settings replace the whole object, not merge."""
        return await service.get_project(project_id)

    @server.tool()
    @_tool_errors
    async def update_project(project_id: str, params: dict | None = None, settings: dict | None = None,
                             title: str | None = None) -> dict:
        """Revise a saved project. Only supplied fields change, but a supplied params or settings
        object replaces the whole object: call get_project first and send the complete object.
        Leave title out to keep the current one. Returns the updated project."""
        fields = {k: v for k, v in {"params": params, "settings": settings, "title": title}.items() if v is not None}
        return await service.update_project(project_id, **fields)

    @server.tool()
    @_tool_errors
    async def duplicate_project(project_id: str, title: str | None = None) -> dict:
        """Copy a saved project under a new id, like Duplicate in the app. The title defaults to
        "<title> copy". Returns the new project; edit the copy, not the original."""
        return await service.duplicate_project(project_id, title)

    @server.tool()
    @_tool_errors
    async def delete_project(project_id: str) -> dict:
        """Delete a saved project; exports already made from it stay. Returns the deleted project."""
        return await service.delete_project(project_id)

    @server.tool(structured_output=False)
    @_tool_errors
    async def preview(project_id: str, mode: Literal["poster", "storyboard", "motion"] = "storyboard") -> list:
        """Look at a project. poster and storyboard return an image you must inspect (storyboard adds
        frame count and times); motion queues a 720p preview with sound for the first 20 s and returns
        a job, which you poll with get_motion. Storyboard is the cheap way to check text and layout."""
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
        """Poll a motion preview started by preview(mode="motion"). Returns status (queued,
        rendering, done, failed or cancelled); when done, url points to an MP4 of the first 20 s
        with the sound mix, with duration and truncated. Keep polling until it leaves queued."""
        return await service.get_motion(preview_id)

    @server.tool()
    @_tool_errors
    async def cancel_motion(preview_id: str) -> dict:
        """Stop a queued or running motion preview and return its record. A finished preview stays."""
        return await service.cancel_motion(preview_id)

    @server.tool(name="export_project")
    @_tool_errors
    async def export_project(project_id: str, format: Literal["mp4", "png", "gif", "webm", "mov"] = "mp4",
                             quality: Literal["draft", "720p", "1080p", "1080p60", "4k"] = "1080p") -> dict:
        """Queue a saved project for export and return the job immediately (status queued); poll
        get_export until done. mp4 is the universal choice; gif loops silently; png is one still;
        webm/mov keep transparency but need settings.background.kind="transparent". draft is for
        checking, 1080p for publishing. The project is validated here, so a bad field errors now."""
        project = await service.get_project(project_id)
        return await service.start_export(project["template"], project["params"], project["settings"],
                                          format=format, quality=quality, title=project["title"])

    @server.tool()
    @_tool_errors
    async def get_export(export_id: str, ctx: Context) -> dict:
        """An export job's status/progress/error and, once done, download_url (absolute) plus
        filename and size. Poll until status is done, failed or cancelled; a failed job's error
        says what broke. Give the person download_url, not a local path."""
        result = await service.get_export(export_id)
        if result.get("url"):
            result["download_url"] = origin(ctx) + result["url"]
        return result

    @server.tool()
    @_tool_errors
    async def list_exports(ctx: Context) -> list[dict]:
        """The export history, newest first, like the app's Exports page. Every finished record
        carries a download_url. Use it when the person asks for "the video I made earlier"."""
        base = origin(ctx)
        records = await service.list_exports()
        for record in records:
            if record.get("url"):
                record["download_url"] = base + record["url"]
        return records

    @server.tool()
    @_tool_errors
    async def cancel_export(export_id: str) -> dict:
        """Stop a queued or running export and return its record (status cancelled). A running job
        may take a moment to stop; wait for the status before removing it."""
        return await service.cancel_export(export_id)

    @server.tool()
    @_tool_errors
    async def retry_export(export_id: str) -> dict:
        """Queue a new export from the request saved on a finished, failed or cancelled record. The
        new job has a new id: poll get_export for it. Records without a stored request answer an
        error; start a fresh export_project instead."""
        return await service.retry_export(export_id)

    @server.tool()
    @_tool_errors
    async def remove_export(export_id: str, delete_file: bool = True) -> dict:
        """Forget a finished, failed or cancelled export. delete_file (the default) also deletes its
        file; false keeps the file in the exports folder. Cancel a running export first."""
        return await service.remove_export(export_id, delete_file=delete_file)

    @server.tool()
    @_tool_errors
    async def add_image(data_base64: str) -> dict:
        """Upload a photo or logo for an image field: PNG, JPEG, GIF, WebP or SVG as base64 (a data
        URL is fine), at most 8 MB. Returns {name, width, height}; put `name` in the template's image
        field (photo, avatar, image, logo). The same picture always gets the same name."""
        return await service.add_image(data_base64)

    @server.tool()
    @_tool_errors
    async def list_icons() -> list[str]:
        """The bundled icon names accepted by template icon fields (e.g. calendar, clock, gift). Use
        one of these instead of emoji in text."""
        return await service.icon_names()

    @server.tool()
    @_tool_errors
    async def upload_audio(data_base64: str, filename: str = "music") -> dict:
        """Upload music (MP3, M4A/AAC, WAV or OGG as base64, at most 50 MB and 10 minutes). Returns
        {name, title, duration, url}; put `name` in settings.sound.music.asset and leave
        music.track empty — the two sources are mutually exclusive."""
        return await service.upload_audio(data_base64, filename)

    @server.tool()
    @_tool_errors
    async def list_music_tracks() -> list[dict]:
        """The original bundled music with audition URLs. Put a track's id in
        settings.sound.music.track and leave music.asset empty."""
        return await service.list_music_tracks()

    return server


class RestBridge:
    """One stdio client proxies the running app, sharing its cache, projects and export queue.

    With a host (--desktop-data), the base URL is resolved for every request, so the app
    opening or closing mid-session is invisible: a connection error restarts or reattaches
    once, then the same request is retried.
    """
    def __init__(self, client, *, host=None):
        self.client = client
        self.host = host

    async def _base(self):
        import asyncio

        if self.host is None:
            return ""
        try:
            return (await asyncio.to_thread(self.host.ensure)).rstrip("/")
        except (OSError, RuntimeError) as exc:
            raise ToolError(f"Could not start Manim Studio ({exc}).") from None

    async def _send(self, method, path, **kwargs):
        import httpx2 as httpx

        base = await self._base()
        try:
            return await self.client.request(method, base + path, **kwargs)
        except httpx.ConnectError:
            # Nothing was sent, so a retry cannot repeat a create or export: the app may
            # have closed or opened since the last call, and ensure() finds the new backend.
            if self.host is None:
                raise
            base = await self._base()
            return await self.client.request(method, base + path, **kwargs)

    async def request(self, method, path, **kwargs):
        import httpx2 as httpx

        try:
            response = await self._send(method, "/api/studio" + path, **kwargs)
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            hint = "The Studio service could not be started" if self.host is not None else "Open the app and check --url"
            raise ToolError(f"Could not reach Manim Studio. {hint} ({type(exc).__name__}).") from None
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

    async def duplicate_project(self, project_id, title=None):
        return await self.request("POST", "/projects/" + quote(project_id, safe="") + "/duplicate",
                                  json={"title": title})

    async def delete_project(self, project_id):
        return await self.request("DELETE", "/projects/" + quote(project_id, safe=""))

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
        import httpx2 as httpx

        try:
            response = await self._send("GET", url)
        except httpx.HTTPError:
            raise ToolError("The preview image could not be loaded.") from None
        if response.is_error:
            raise ToolError("The preview image could not be loaded.")
        return response.content

    async def start_export(self, template, params, settings, **fields):
        return await self.request("POST", "/exports", json={"template": template, "params": params, "settings": settings, **fields})

    async def list_exports(self):
        return await self.request("GET", "/exports")

    async def get_export(self, export_id):
        return await self.request("GET", "/exports/" + quote(export_id, safe=""))

    async def cancel_export(self, export_id):
        return await self.request("DELETE", "/exports/" + quote(export_id, safe=""))

    async def retry_export(self, export_id):
        return await self.request("POST", "/exports/" + quote(export_id, safe="") + "/retry")

    async def remove_export(self, export_id, delete_file=True):
        path = "/exports/" + quote(export_id, safe="")
        if delete_file:
            return await self.request("DELETE", path, params={"remove": True})
        return await self.request("POST", path + "/forget")

    async def add_image(self, data):
        return await self.request("POST", "/images", json={"data": data})

    async def icon_names(self):
        return await self.request("GET", "/icons")

    async def upload_audio(self, data, filename="music"):
        return await self.request("POST", "/audio", json={"data": data, "filename": filename})

    async def list_music_tracks(self):
        return await self.request("GET", "/music-tracks")


def main():
    import asyncio
    import httpx2 as httpx

    parser = argparse.ArgumentParser(description="Connect an MCP client to Manim Studio over stdio (the desktop mode starts it in the background).")
    parser.add_argument("--url", default=os.environ.get("COMPOSER_URL", "http://127.0.0.1:8000"),
                        help="Base URL of the running app (ignored with --desktop-data).")
    parser.add_argument("--token-file", help="Read the app's workspace/studio/mcp-token (or set COMPOSER_TOKEN).")
    parser.add_argument("--desktop-data",
                        help="Data folder holding workspace/, desktop-port and desktop.lock; starts the app's "
                             "backend in the background when the app is closed.")
    parser.add_argument("--app-root", help="Application root; defaults to two levels above backend/studio.")
    args = parser.parse_args()

    if args.desktop_data:
        if args.token_file:
            parser.error("--desktop-data reads the workspace token itself; do not pass --token-file.")
        data = os.path.abspath(os.path.expanduser(args.desktop_data))
        root = os.path.abspath(args.app_root) if args.app_root else os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        for folder in ("desktop", "shell"):
            candidate = os.path.join(root, folder)
            if os.path.isfile(os.path.join(candidate, "agent_host.py")):
                sys.path.insert(0, candidate)
                break
        else:
            parser.error(f"--desktop-data needs agent_host.py under {root}/desktop or {root}/shell")
        from agent_host import AgentHost

        host = AgentHost(root, data)
        client = httpx.AsyncClient(timeout=90, headers={"Authorization": f"Bearer {host.token}"}, trust_env=False)

        async def run_desktop():
            try:
                await create_server(RestBridge(client, host=host), base_url=host.base_url).run_stdio_async()
            finally:
                await client.aclose()
                host.close()
        asyncio.run(run_desktop())
        return

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
