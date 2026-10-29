"""REST routes for the template studio (``/api/studio``): a thin layer over ``studio.service``.

Bad input answers 422 ``{"detail": message, "errors": [{"field", "message"}]}``; other
service errors answer their ``status`` with ``{"detail": message}``. Bodies are read as
raw JSON objects and validated by the service, so REST and MCP share one validator
(and one error shape). main.py includes this router before the frontend mount; the
app's origin/host middleware and body-size limit apply to it like to every route.
"""

from __future__ import annotations

import functools

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from . import service as service_module
from .errors import StudioError
from .registry import TemplateError

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
            return JSONResponse({"detail": str(exc)}, status_code=exc.status)

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


@router.post("/preview")
@_errors
async def post_preview(request: Request):
    body = await _body(request, ("template", "params", "settings", "mode", "short"))
    result = await get_service().preview(body.get("template"), body.get("params"), body.get("settings"),
                                         body.get("mode", "poster"), body.get("short"))
    result.pop("path", None)  # host paths stay on the host
    return result


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
    body = await _body(request, ("title", "params", "settings"))
    return await get_service().update_project(project_id, **body)


@router.delete("/projects/{project_id}")
@_errors
async def delete_project(project_id: str):
    return await get_service().delete_project(project_id)


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
