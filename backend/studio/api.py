"""REST routes for the template studio (``/api/studio``): a thin layer over ``studio.service``.

Bad input answers 422 ``{"detail": message, "errors": [{"field", "message"}]}``; other
service errors answer their ``status`` with ``{"detail": message}``. Bodies are read as
raw JSON objects and validated by the service, so REST and MCP share one validator
(and one error shape). main.py includes this router before the frontend mount; the
app's origin/host middleware and body-size limit apply to it like to every route.
"""

from __future__ import annotations

import asyncio
import functools
import ipaddress
import os
import threading
import time
import urllib.request
from urllib.parse import quote

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

from . import preferences as preferences_module
from . import service as service_module
from . import setup_components as setup_components_module
from . import setup_mcp as setup_mcp_module
from . import updates as updates_module
from .errors import StudioError
from .registry import TemplateError
from .version import APP_VERSION

router = APIRouter(prefix="/api/studio", tags=["studio"])


def get_service():
    """The service the routes use (tests swap ``studio.service.service``)."""
    return service_module.service


def _errors(fn):
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except TemplateError as exc:
            return JSONResponse({"detail": str(exc), "errors": exc.errors}, status_code=422)
        except StudioError as exc:
            body = {"detail": str(exc)}
            project = getattr(exc, "project", None)  # a stale save answers with the current project
            if project is not None:
                body["project"] = project
            return JSONResponse(body, status_code=exc.status)

    return wrapper


async def _body(request: Request, allowed: tuple) -> dict:
    try:
        data = await request.json()
    except Exception:  # noqa: BLE001 - any decode problem is the client's
        data = None
    if not isinstance(data, dict):
        raise TemplateError("The request body must be a JSON object.",
                            [{"field": "body", "message": "Send a JSON object."}])
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise TemplateError(f"Unknown field{'s' if len(unknown) > 1 else ''}: {', '.join(unknown)}.",
                            [{"field": key, "message": "Unknown field."} for key in unknown])
    return data


@router.get("/catalog")
@_errors
async def get_catalog():
    return await get_service().catalog()


@router.get("/templates/{template_id}")
@_errors
async def get_template(template_id: str):
    return await get_service().template_info(template_id)


@router.get("/preferences")
@_errors
async def get_preferences():
    """Choices kept with the workspace, so they survive a restart of the desktop app."""
    return await get_service().get_preferences()


@router.patch("/preferences")
@_errors
async def patch_preferences(request: Request):
    """Merge a partial preferences object; invalid values answer 422 with field errors."""
    body = await _body(request, preferences_module.PREFERENCE_KEYS)
    return await get_service().update_preferences(body)


def get_setup_mcp():
    """The AI-app connector the setup routes use (tests swap this)."""
    return setup_mcp_module.McpSetup()


def get_setup_components():
    """The add-on detector and installer of the service's workspace (tests swap this)."""
    return get_service().setup_manager()


class _SetupForbidden(StudioError):
    status = 403


def _require_local(request: Request) -> None:
    """Connecting apps, installing add-ons and opening folders are for this computer only."""
    host = request.client.host if request.client else ""
    if host in ("", "testclient", "localhost"):
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise _SetupForbidden("This can only be changed from this computer.")


def default_connection(base_url: str) -> dict:
    """The record for an app that installed no builder of its own (the bare router)."""
    service = get_service()
    return setup_mcp_module.connection_record(base_url, service.workspace_dir, service.app_root)


# The app installs its own builder where it includes this router (main.py), so the
# setup routes never import the server to ask it what connection it publishes.
connection_provider = default_connection


def set_connection_provider(provider) -> None:
    """Install the record builder the setup routes read."""
    global connection_provider
    connection_provider = provider


async def _connection(request: Request) -> dict:
    """The record GET /api/studio/connection publishes, so a saved entry cannot drift."""
    return connection_provider(str(request.base_url).rstrip("/"))


def _setup_status(manager, setup, connection: dict) -> dict:
    return {
        "platform": manager.platform,
        "mode": manager.mode,
        "version": APP_VERSION,
        "components": manager.components(),
        "ai_apps": setup.entries(connection),
        "data_folder": manager.workspace,
    }


@router.get("/setup/status")
@_errors
async def get_setup_status(request: Request):
    """What is ready, what is optional, and which AI apps are already connected."""
    connection = await _connection(request)
    return await asyncio.to_thread(_setup_status, get_setup_components(), get_setup_mcp(), connection)


@router.post("/setup/ai-apps/{app_id}/connect")
@_errors
async def post_setup_connect(app_id: str, request: Request):
    """Add this app's entry to one AI assistant's settings (a backup is kept once)."""
    _require_local(request)
    connection = await _connection(request)
    return await asyncio.to_thread(get_setup_mcp().connect, app_id, connection)


@router.delete("/setup/ai-apps/{app_id}/connect")
@_errors
async def delete_setup_connect(app_id: str, request: Request):
    """Remove only our entry from that app's settings."""
    _require_local(request)
    connection = await _connection(request)
    return await asyncio.to_thread(get_setup_mcp().disconnect, app_id, connection)


@router.post("/setup/components/{component_id}/install", status_code=202)
@_errors
async def post_setup_install(component_id: str, request: Request):
    """Start one add-on download; progress shows in GET /setup/status."""
    _require_local(request)
    return await asyncio.to_thread(get_setup_components().install, component_id)


@router.post("/setup/reveal-data-folder", status_code=204)
@_errors
async def post_setup_reveal(request: Request):
    """Show the workspace's data folder in the system's file manager."""
    _require_local(request)
    await asyncio.to_thread(setup_components_module.reveal_folder, get_service().workspace_dir)
    return Response(status_code=204)


_update_managers: dict = {}
_update_managers_lock = threading.Lock()


def get_update_manager() -> updates_module.UpdateManager:
    """The one update state of the service's workspace (tests swap this)."""
    workspace = os.path.abspath(get_service().workspace_dir)
    with _update_managers_lock:
        manager = _update_managers.get(workspace)
        if manager is None:
            manager = updates_module.UpdateManager(workspace)
            _update_managers[workspace] = manager
        return manager


def _close_desktop_app(request: Request) -> None:
    """Ask the desktop shell to close through its own authenticated shutdown route."""
    token = os.environ.get("MANIM_API_TOKEN", "")
    if not token:
        return
    base = str(request.base_url).rstrip("/")

    def send() -> None:
        # The answer to this request reaches the page first; then the app closes.
        time.sleep(0.5)
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            opener.open(urllib.request.Request(
                base + "/__desktop__/shutdown", method="POST",
                headers={"Authorization": f"Bearer {token}", "Origin": base}), timeout=3).close()
        except OSError:
            pass

    threading.Thread(target=send, daemon=True, name="studio-update-close").start()


@router.get("/setup/update")
@_errors
async def get_setup_update():
    """The update state; the once-a-day check starts here, never on a timer."""
    return await asyncio.to_thread(updates_module.update_status, get_update_manager())


@router.post("/setup/update/check")
@_errors
async def post_setup_update_check(request: Request):
    """Check now, even when the automatic daily check already ran."""
    _require_local(request)
    return await asyncio.to_thread(get_update_manager().check, True)


@router.post("/setup/update/download")
@_errors
async def post_setup_update_download(request: Request):
    """Fetch the verified installer in the background; progress shows in GET update."""
    _require_local(request)
    return await asyncio.to_thread(get_update_manager().download)


@router.post("/setup/update/install")
@_errors
async def post_setup_update_install(request: Request):
    """Start the installer and let the app close; an export in flight is never interrupted."""
    _require_local(request)
    exports = await get_service().list_exports()
    busy = any(isinstance(item, dict) and item.get("status") in ("queued", "rendering")
               for item in exports)
    result = await asyncio.to_thread(get_update_manager().install, busy)
    _close_desktop_app(request)
    return result


@router.post("/batches/parse")
@_errors
async def post_batch_parse(request: Request):
    """Read a list (a file or pasted text) and suggest which column fills which field.

    Sending ``rows`` and ``mapping`` instead checks those rows again and returns the same
    per-row problems a batch would skip, without creating anything.
    """
    body = await _body(request, ("template", "filename", "data", "text", "rows", "mapping",
                                 "params", "settings", "title_column"))
    fields = {key: value for key, value in body.items() if key != "template"}
    return await get_service().parse_batch(body.get("template"), **fields)


@router.post("/batches", status_code=202)
@_errors
async def post_batch(request: Request):
    """Queue one export per usable row; rows with problems come back in ``row_errors``."""
    body = await _body(request, ("template", "params", "settings", "mapping", "rows",
                                 "title_column", "format", "quality"))
    return await get_service().start_batch(
        body.get("template"), params=body.get("params"), settings=body.get("settings"),
        mapping=body.get("mapping"), rows=body.get("rows"), title_column=body.get("title_column"),
        format=body.get("format", "mp4"), quality=body.get("quality", "1080p"))


@router.get("/batches/{batch_id}")
@_errors
async def get_batch(batch_id: str):
    """A batch's name, totals and how many of its exports are in each state."""
    return await get_service().get_batch(batch_id)


@router.post("/batches/{batch_id}/cancel")
@_errors
async def post_batch_cancel(batch_id: str):
    """Cancel the batch's queued and running exports; finished ones stay."""
    return await get_service().cancel_batch(batch_id)


@router.post("/batches/{batch_id}/retry")
@_errors
async def post_batch_retry(batch_id: str):
    """Queue the batch's failed rows again, keeping them in the same batch."""
    return await get_service().retry_batch(batch_id)


@router.get("/posters/{key}.png")
@_errors
async def get_poster(key: str):
    return FileResponse(get_service().poster_path(key), media_type="image/png",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=31536000, immutable"})


@router.get("/peeks/{key}.mp4")
@_errors
async def get_peek(key: str):
    return FileResponse(get_service().peek_path(key), media_type="video/mp4",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=31536000, immutable"})


@router.post("/preview")
@_errors
async def post_preview(request: Request):
    body = await _body(request, ("template", "params", "settings", "mode", "short"))
    result = await get_service().preview(body.get("template"), body.get("params"), body.get("settings"),
                                         body.get("mode", "poster"), body.get("short"))
    result.pop("path", None)  # host paths stay on the host
    return result


@router.post("/length")
@_errors
async def post_length(request: Request):
    """The real duration for these params, measured without rendering (null when unavailable)."""
    body = await _body(request, ("template", "params", "settings"))
    return await get_service().estimate_length(body.get("template"), body.get("params"), body.get("settings"))


@router.post("/exports", status_code=202)
@_errors
async def post_export(request: Request):
    body = await _body(request, ("template", "params", "settings", "format", "quality", "title"))
    return await get_service().start_export(body.get("template"), body.get("params"), body.get("settings"),
                                            format=body.get("format", "mp4"), quality=body.get("quality", "1080p"),
                                            title=body.get("title"))


@router.post("/motion", status_code=202)
@_errors
async def post_motion(request: Request):
    body = await _body(request, ("project", "template", "params", "settings"))
    return await get_service().start_motion(body.get("project"), body.get("template"),
                                             body.get("params"), body.get("settings"))


@router.get("/motion/{preview_id}")
@_errors
async def get_motion(preview_id: str):
    return await get_service().get_motion(preview_id)


@router.delete("/motion/{preview_id}")
@_errors
async def delete_motion(preview_id: str):
    return await get_service().cancel_motion(preview_id)


@router.get("/exports")
@_errors
async def get_exports():
    return await get_service().list_exports()


@router.get("/exports/{export_id}")
@_errors
async def get_export(export_id: str):
    return await get_service().get_export(export_id)


@router.delete("/exports/{export_id}")
@_errors
async def delete_export(export_id: str, remove: bool = False):
    """Cancel a queued or running export; ``?remove=true`` forgets a finished one and deletes its file."""
    svc = get_service()
    if remove:
        return await svc.remove_export(export_id)
    return await svc.cancel_export(export_id)


@router.post("/exports/{export_id}/retry", status_code=202)
@_errors
async def post_export_retry(export_id: str):
    """Queue a new export from the request saved on a finished record."""
    return await get_service().retry_export(export_id)


@router.post("/exports/{export_id}/forget")
@_errors
async def post_export_forget(export_id: str):
    """Forget an export from the history and keep its file."""
    return await get_service().remove_export(export_id, delete_file=False)


@router.get("/host")
@_errors
async def get_host():
    """Which finished-file actions this computer supports."""
    return get_service().host_capabilities()


@router.post("/exports/{export_id}/reveal", status_code=204)
@_errors
async def post_export_reveal(export_id: str):
    """Show the finished file selected in the system's file manager."""
    await get_service().reveal_export(export_id)
    return Response(status_code=204)


@router.post("/exports/{export_id}/copy", status_code=204)
@_errors
async def post_export_copy(export_id: str):
    """Put the finished file itself on the clipboard."""
    await get_service().copy_export_file(export_id)
    return Response(status_code=204)


@router.get("/projects")
@_errors
async def get_projects():
    return await get_service().list_projects()


@router.post("/projects", status_code=201)
@_errors
async def post_project(request: Request):
    body = await _body(request, ("title", "template", "params", "settings"))
    return await get_service().create_project(body.get("template"), body.get("params"), body.get("settings"),
                                              body.get("title"))


@router.get("/projects/{project_id}")
@_errors
async def get_project(project_id: str):
    return await get_service().get_project(project_id)


@router.put("/projects/{project_id}")
@_errors
async def put_project(project_id: str, request: Request):
    body = await _body(request, ("title", "params", "settings", "base_revision"))
    return await get_service().update_project(project_id, **body)


@router.delete("/projects/{project_id}")
@_errors
async def delete_project(project_id: str):
    return await get_service().delete_project(project_id)


@router.post("/projects/{project_id}/duplicate", status_code=201)
@_errors
async def post_project_duplicate(project_id: str, request: Request):
    body = await _body(request, ("title",))
    return await get_service().duplicate_project(project_id, body.get("title"))


def _discard_portable_file(path: str) -> None:
    """Remove the temporary zip once its download has been sent."""
    try:
        os.unlink(path)
    except OSError:
        pass


@router.get("/projects/{project_id}/file")
@_errors
async def get_project_file(project_id: str):
    """Download one saved project as a single .manimstudio file."""
    result = await get_service().project_file(project_id)
    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}
    if result.get("note"):
        headers["X-Studio-Note"] = quote(result["note"], safe="")
    return FileResponse(result["path"], media_type="application/zip", filename=result["filename"],
                        headers=headers,
                        background=BackgroundTask(_discard_portable_file, result["path"]))


@router.get("/projects/{project_id}/file/info")
@_errors
async def get_project_file_info(project_id: str):
    """The download's name and any plain note about files missing from this computer."""
    return await get_service().project_file_info(project_id)


@router.post("/projects/open", status_code=201)
@_errors
async def post_project_open(request: Request):
    """Open an uploaded .manimstudio file as a new project (base64 like a list upload)."""
    body = await _body(request, ("data", "filename"))
    return await get_service().open_project_file(body.get("data"), body.get("filename") or "")


@router.post("/images", status_code=201)
@_errors
async def post_image(request: Request):
    """An image for a template's image field, sent as base64 (agents use this; people upload files)."""
    body = await _body(request, ("data",))
    return await get_service().add_image(body.get("data"))


@router.get("/icons")
@_errors
async def get_icons():
    return await get_service().icon_names()


@router.get("/music-tracks")
@_errors
async def get_music_tracks():
    return await get_service().list_music_tracks()


@router.get("/sounds/{kind}/{name}.wav")
@_errors
async def get_sound(kind: str, name: str):
    return FileResponse(await get_service().sound_file(kind, name), media_type="audio/wav",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"})


@router.post("/audio", status_code=201)
@_errors
async def post_audio(request: Request):
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        from .sound import MAX_AUDIO_BYTES
        async with request.form(max_files=1, max_fields=0) as form:
            upload = form.get("file")
            if upload is None or not hasattr(upload, "read"):
                raise TemplateError("Choose an audio file.")
            return await get_service().upload_audio(await upload.read(MAX_AUDIO_BYTES + 1), upload.filename)
    body = await _body(request, ("data", "filename"))
    return await get_service().upload_audio(body.get("data"), body.get("filename", "music"))


@router.get("/audio/{name}")
@_errors
async def get_audio(name: str):
    return FileResponse(get_service().audio_path(name), media_type="audio/flac" if name.endswith(".flac") else "audio/wav",
                        headers={"X-Content-Type-Options": "nosniff"})


@router.get("/images/{name}")
@_errors
async def get_image(name: str):
    """Optional crop provenance; image field values remain ordinary asset names."""
    return await get_service().image_info(name)


@router.post("/images/{name}/crop")
@_errors
async def post_image_crop(name: str, request: Request):
    body = await _body(request, ("source", "position", "ratio", "shape"))
    return await get_service().save_image_crop(name, body)


@router.get("/icons/{name}.svg")
@_errors
async def get_icon(name: str):
    path = get_service().icon_path(name)
    # Bundled files, but SVG is a document: no scripts, no sniffing.
    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=300",
               "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox"}
    return FileResponse(path, media_type="image/svg+xml", headers=headers)
