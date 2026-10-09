"""FastAPI backend for Manim Composer: workspace files, diagnostics, and live renders."""

import asyncio
import hashlib
import json
import mimetypes
import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional
from urllib.parse import quote

# Ensure backend directory is in python search path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from diagnostics import get_binary_paths, get_cached_profile, write_manim_config_file
from executor import OUTPUT_EXTENSIONS, ManimExecutor, keep_box_width, media_rel_path, output_kind
from origins import is_host_allowed, is_origin_allowed, is_peer_allowed
from scene_parser import get_render_names, get_scene_animations, get_scenes_from_code, get_syntax_error
from workspace_paths import (
    UnsafePathError,
    find_case_insensitive_match,
    nfc_filename,
    safe_basename,
    safe_join,
    to_script_name,
    validate_new_filename,
)
from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

APP_VERSION = "1.1.0"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_DIR = os.path.join(BASE_DIR, "workspace")
MEDIA_DIR = os.path.join(WORKSPACE_DIR, "media")
ASSETS_DIR = os.path.join(WORKSPACE_DIR, "assets")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend", "dist")
FRONTEND_ASSETS_DIR = os.path.join(FRONTEND_DIR, "assets")

TEMP_PREFIX = "_temp_run_"
MEDIA_SUBDIRS = ("videos", "images")

# Max size for code sent to /api/save, /api/parse-code, and the render socket.
MAX_CODE_BYTES = int(os.environ.get("MANIM_MAX_CODE_BYTES", str(2 * 1024 * 1024)))
# Raw request / WebSocket message cap. The code limit above is checked on the decoded
# code itself; JSON escaping can grow it up to 6x (control chars become \u00XX).
MAX_REQUEST_BODY_BYTES = int(
    os.environ.get("MANIM_MAX_REQUEST_BYTES", str(6 * MAX_CODE_BYTES + 64 * 1024))
)


def _body_too_large() -> str:
    return f"Request body exceeds maximum size ({MAX_REQUEST_BODY_BYTES} bytes)."


ALLOWED_QUALITIES = frozenset({"l", "m", "h", "k"})

ALLOWED_ASSET_EXTENSIONS = {
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".mp3",
    ".wav",
    ".ogg",
    ".m4a",
    ".ttf",
    ".otf",
}
MAX_ASSET_SIZE_BYTES = 50 * 1024 * 1024  # 50MB

DEFAULT_SCRIPT_NAME = "example.py"
# Written once the starter script has been offered, so deleting example.py sticks.
SEED_MARKER_NAME = ".composer-initialized"
# A download-only render that nobody fetched is removed after this many seconds.
TEMP_DOWNLOAD_TTL_SECONDS = int(os.environ.get("MANIM_TEMP_DOWNLOAD_TTL", "3600"))
DEFAULT_SCRIPT = '''from manim import *


class SquareToCircle(Scene):
    """The classic first Manim scene: a square morphs into a circle."""

    def construct(self):
        square = Square(side_length=3, color=BLUE).rotate(PI / 4)
        circle = Circle(radius=1.5, color=PINK).set_fill(PINK, opacity=0.35)

        self.play(Create(square))
        self.play(Transform(square, circle))
        self.wait(0.5)
        self.play(FadeOut(square))


class TitleCard(Scene):
    """Animated title text. Text() uses Pango, so it works without LaTeX."""

    def construct(self):
        title = Text("Manim Composer", font_size=64, weight=BOLD)
        underline = Underline(title, color=BLUE, buff=0.2)
        subtitle = Text("Write a scene. Press render.", font_size=30, color=GRAY_B)
        subtitle.next_to(underline, DOWN, buff=0.5)

        self.play(Write(title))
        self.play(Create(underline), FadeIn(subtitle, shift=UP * 0.3))
        self.wait(1)
        self.play(FadeOut(VGroup(title, underline, subtitle), shift=DOWN * 0.3))


class SineWave(Scene):
    """Plot a function on axes and trace it with a moving dot."""

    def construct(self):
        axes = Axes(
            x_range=[0, 2 * PI, PI / 2],
            y_range=[-1.5, 1.5, 0.5],
            x_length=10,
            y_length=4,
            tips=False,
        )
        curve = axes.plot(np.sin, color=YELLOW)
        dot = Dot(axes.c2p(0, 0), color=YELLOW)

        self.play(Create(axes))
        self.play(Create(curve), MoveAlongPath(dot, curve), run_time=3, rate_func=linear)
        self.wait(0.5)
'''


# Importing this module must not touch render scratch files. Startup maintenance
# runs from the lifespan hook; tests turn it off so a pytest import can't kill
# a render that is already in progress.
RUN_STARTUP_MAINTENANCE = True

# One render at a time unless MANIM_MAX_CONCURRENT_RENDERS says otherwise.
# Parallel renders share Manim's text cache and the same output path.
MAX_CONCURRENT_RENDERS = max(1, int(os.environ.get("MANIM_MAX_CONCURRENT_RENDERS", "1")))
_render_slots: Optional[asyncio.Semaphore] = None
# How long a cancelled render may take to wind down before its task is cancelled outright.
STOP_GRACE_SECONDS = 30.0


def _render_semaphore() -> asyncio.Semaphore:
    global _render_slots
    if _render_slots is None:
        _render_slots = asyncio.Semaphore(MAX_CONCURRENT_RENDERS)
    return _render_slots


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    if RUN_STARTUP_MAINTENANCE:
        _sweep_temp_renders()
        write_manim_config_file(WORKSPACE_DIR, get_cached_profile())
    yield


app = FastAPI(title="Manim Composer API", version=APP_VERSION, lifespan=_lifespan)


def _request_allowed(headers, peer: Optional[str] = None) -> bool:
    try:
        if not is_peer_allowed(peer):
            return False
        host = headers.get("host")
        return is_host_allowed(host) and is_origin_allowed(headers.get("origin"), host)
    except (ValueError, TypeError):
        # A header the policy cannot parse is refused (403), never a 500.
        return False


def _peer_host(client) -> Optional[str]:
    return client.host if client is not None else None


@app.middleware("http")
async def reject_untrusted_requests(request: Request, call_next):
    if not _request_allowed(request.headers, _peer_host(request.client)):
        return JSONResponse({"detail": "Request origin or host not allowed."}, status_code=403)
    return await call_next(request)


class LimitCodeBodyMiddleware:
    """Reject oversized script uploads from Content-Length, before the body is parsed.

    The code itself is checked against MANIM_MAX_CODE_BYTES by the endpoint; this is
    only a raw-size backstop (MAX_REQUEST_BODY_BYTES) sized for JSON escaping.
    """

    PATHS = {"/api/save", "/api/parse-code"}

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") not in self.PATHS or scope.get("method") not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return
        limit = MAX_REQUEST_BODY_BYTES
        headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope.get("headers", [])}
        declared = headers.get("content-length")
        if declared is not None:
            try:
                too_big = int(declared) > limit
            except ValueError:
                too_big = True
            if too_big:
                response = JSONResponse(
                    {"detail": _body_too_large()},
                    status_code=413,
                )
                await response(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return

        chunks = []
        total = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                # http.disconnect: the client went away mid-body. Nothing can be
                # answered, and receive() would keep returning the same message.
                return
            total += len(message.get("body", b""))
            if total > limit:
                response = JSONResponse(
                    {"detail": _body_too_large()},
                    status_code=413,
                )
                await response(scope, receive, send)
                return
            chunks.append(message)
            if not message.get("more_body", False):
                break

        index = 0

        async def replay():
            nonlocal index
            if index < len(chunks):
                item = chunks[index]
                index += 1
                return item
            # The body has been replayed; later reads wait for the real disconnect.
            return await receive()

        await self.app(scope, replay, send)


app.add_middleware(LimitCodeBodyMiddleware)


class _PolicyCORSMiddleware(CORSMiddleware):
    """CORS headers for exactly the cross-origin callers the origin policy accepts."""

    def is_allowed_origin(self, origin: str) -> bool:
        return is_origin_allowed(origin)


app.add_middleware(
    _PolicyCORSMiddleware,
    allow_origins=[],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Startup
# --------------------------------------------------------------------------- #

for path in [WORKSPACE_DIR, MEDIA_DIR, ASSETS_DIR]:
    os.makedirs(path, exist_ok=True)


def _sweep_temp_renders() -> None:
    """Remove scratch scripts and outputs left behind by renders from a previous run."""
    try:
        for entry in os.scandir(WORKSPACE_DIR):
            if entry.is_file() and entry.name.startswith(TEMP_PREFIX) and entry.name.endswith(".py"):
                os.remove(entry.path)
    except OSError:
        pass
    for sub in MEDIA_SUBDIRS:
        root = os.path.join(MEDIA_DIR, sub)
        if not os.path.isdir(root):
            continue
        for entry in os.scandir(root):
            if entry.is_dir() and entry.name.startswith(TEMP_PREFIX):
                shutil.rmtree(entry.path, ignore_errors=True)


# Rendered videos are served from /media. User uploads are served by the /assets
# route below, which prefers the Vite bundle (frontend/dist/assets) and falls
# back to workspace/assets — mounting uploads at /assets would shadow the SPA.
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")


@app.get("/assets/{asset_path:path}")
def serve_asset(asset_path: str):
    """Serve Vite build assets first, then workspace user uploads."""
    if os.path.isdir(FRONTEND_ASSETS_DIR):
        try:
            spa_file = safe_join(FRONTEND_ASSETS_DIR, asset_path)
            if os.path.isfile(spa_file):
                return FileResponse(spa_file)
        except UnsafePathError:
            pass
    try:
        user_file = safe_join(ASSETS_DIR, asset_path)
    except UnsafePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not os.path.isfile(user_file):
        raise HTTPException(status_code=404, detail="Asset not found")
    # SVGs are same-origin documents. Without a sandbox policy, a script inside
    # an uploaded SVG runs with the app's origin when the file is opened directly.
    headers = {"X-Content-Type-Options": "nosniff"}
    if user_file.lower().endswith(".svg"):
        headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    return FileResponse(user_file, headers=headers)


def _parsed(code: str) -> dict:
    result = {"scenes": get_scenes_from_code(code), "animations": get_scene_animations(code)}
    error = get_syntax_error(code)
    if error:
        result["syntax_error"] = error
    return result


def _render_block_reason(code: str, scene_name: str) -> Optional[str]:
    """Why this code cannot be rendered, or None when Manim should be started."""
    error = get_syntax_error(code)
    if error:
        return f"Syntax error on line {error['line']}: {error['message']}"
    # Only reject what the AST can prove. Anything else (aliased or factory-made
    # bases, Slide, classes under if/try) goes to Manim, and a run that writes
    # nothing is still reported as failed afterwards.
    scenes = get_scenes_from_code(code)
    if scene_name in scenes:
        return None
    info = get_render_names(code)
    if not info["has_class"] and not info["open_namespace"]:
        return "No Scene class found. Add one, for example: class Intro(Scene):"
    if scene_name in info["names"] or info["open_namespace"]:
        return None
    found = ", ".join(scenes) if scenes else "no Scene classes"
    return f"Scene '{scene_name}' is not in this file. Found: {found}."


def _render_scene_warning(code: str, scene_name: str) -> Optional[str]:
    """A note for scenes the AST could not confirm; the render still runs."""
    if get_syntax_error(code) or scene_name in get_scenes_from_code(code):
        return None
    return (
        f"Couldn't confirm that '{scene_name}' is a Scene subclass from the code alone; "
        "letting Manim decide."
    )


def _ensure_code_within_limit(code: str) -> None:
    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Code payload exceeds maximum size ({MAX_CODE_BYTES} bytes).",
        )


# --------------------------------------------------------------------------- #
# Status & diagnostics
# --------------------------------------------------------------------------- #


@app.get("/api/status")
@app.get("/api/health")
def read_status():
    return {
        "status": "online",
        "service": "Manim Composer API",
        "version": APP_VERSION,
        "docs": "/docs",
    }


@app.get("/api/diagnostics")
def get_diagnostics():
    """Hardware profile (cached) plus freshly detected dependencies.

    Dependency lookup is cheap and must not be cached, otherwise an install
    started from the setup dialog would not show up for minutes.
    """
    profile = get_cached_profile()
    profile["dependencies"] = get_binary_paths()
    profile["max_code_bytes"] = MAX_CODE_BYTES
    return profile


# --------------------------------------------------------------------------- #
# Workspace files
# --------------------------------------------------------------------------- #


def _list_scripts() -> list:
    scripts = []
    try:
        with os.scandir(WORKSPACE_DIR) as entries:
            for entry in entries:
                if entry.is_file() and entry.name.endswith(".py") and not entry.name.startswith(TEMP_PREFIX):
                    try:
                        scripts.append({"name": entry.name, "size": entry.stat().st_size, "type": "script"})
                    except OSError:
                        pass
    except OSError:
        pass
    return sorted(scripts, key=lambda item: item["name"].lower())


def _list_assets() -> list:
    assets = []
    try:
        with os.scandir(ASSETS_DIR) as entries:
            for entry in entries:
                if entry.is_file():
                    try:
                        assets.append(
                            {
                                "name": entry.name,
                                "size": entry.stat().st_size,
                                "type": "asset",
                                "url": f"/assets/{quote(entry.name)}",
                            }
                        )
                    except OSError:
                        pass
    except OSError:
        pass
    return sorted(assets, key=lambda item: item["name"].lower())


def _media_item(full_path: str) -> Optional[dict]:
    rel_path = os.path.relpath(full_path, MEDIA_DIR).replace("\\", "/")
    parts = rel_path.split("/")
    try:
        stat = os.stat(full_path)
    except OSError:
        return None
    name = parts[-1]
    stem = os.path.splitext(name)[0]
    script = parts[1] if len(parts) >= 3 else None
    quality = parts[2] if parts[0] == "videos" and len(parts) >= 4 else None
    return {
        "name": name,
        "size": stat.st_size,
        "type": output_kind(name),
        "url": "/media/" + "/".join(quote(part) for part in parts),
        "path": rel_path,
        "script": script,
        "scene": stem.split("_ManimCE_")[0],
        "quality": quality,
        "modified": stat.st_mtime,
    }


def _list_media() -> list:
    media = []
    for sub in MEDIA_SUBDIRS:
        root_dir = os.path.join(MEDIA_DIR, sub)
        if not os.path.isdir(root_dir):
            continue
        for root, dirs, files in os.walk(root_dir):
            # Prune scratch output and Manim's per-animation chunks.
            dirs[:] = [d for d in dirs if d != "partial_movie_files" and not d.startswith(TEMP_PREFIX)]
            for name in files:
                if name.lower().endswith(OUTPUT_EXTENSIONS):
                    item = _media_item(os.path.join(root, name))
                    if item:
                        media.append(item)
    return sorted(media, key=lambda item: item["modified"], reverse=True)


@app.get("/api/files")
def get_files():
    """List workspace scripts, uploaded assets, and rendered media (newest first)."""
    _seed_starter_script_once()
    _sweep_stale_temp_downloads()
    return {"scripts": _list_scripts(), "assets": _list_assets(), "media": _list_media()}


def _seed_starter_script_once() -> None:
    """Write example.py into an empty workspace on first setup only, not after a delete."""
    marker = os.path.join(WORKSPACE_DIR, SEED_MARKER_NAME)
    if os.path.exists(marker):
        return
    try:
        if not _list_scripts():
            with open(os.path.join(WORKSPACE_DIR, DEFAULT_SCRIPT_NAME), "w", encoding="utf-8") as f:
                f.write(DEFAULT_SCRIPT)
        with open(marker, "w", encoding="utf-8") as f:
            f.write("The starter script has been created; delete this file to get it back.\n")
    except OSError:
        pass


def _script_path(filename: str, *, new: bool = False) -> tuple:
    """Validate a script name. ``new=True`` applies the rules for names being created."""
    try:
        if new:
            name = validate_new_filename(filename, required_suffix=".py", forbid_temp_prefix=True)
        else:
            name = safe_basename(filename, required_suffix=".py")
        return name, safe_join(WORKSPACE_DIR, name)
    except UnsafePathError as exc:
        raise HTTPException(status_code=400, detail=_bad_script_name_detail(filename, exc))


def _is_existing_script(filename) -> bool:
    """True if *filename* names a file that is already in the workspace (legacy names too)."""
    try:
        return os.path.isfile(safe_join(WORKSPACE_DIR, safe_basename(filename)))
    except (UnsafePathError, TypeError, ValueError):
        return False


def _bad_script_name_detail(filename, exc: Exception) -> str:
    """Files that exist under a name today's rules forbid can still be opened and
    renamed; saving or rendering them says so instead of a bare refusal."""
    if _is_existing_script(filename):
        return f"Rename this file to save or render it: {exc}"
    return f"Invalid script filename: {exc}"


def _new_script_path(raw: str) -> tuple:
    """Save / rename target: ``Foo.PY`` -> ``Foo.py`` (NFC), then the rules for new names."""
    name = to_script_name(raw)
    if name != raw and raw.lower().endswith(".py") and _is_existing_script(raw):
        raise HTTPException(
            status_code=400,
            detail=f"Rename this file to save or render it: it would be saved as '{name}'.",
        )
    return _script_path(name, new=True)


def _reject_case_collision(directory: str, name: str) -> None:
    """409 when another file differs from *name* only by letter case."""
    clash = find_case_insensitive_match(directory, name)
    if clash:
        raise HTTPException(
            status_code=409,
            detail=f"'{clash}' already exists. File names that differ only by case are not allowed.",
        )


def _os_error_detail(exc: OSError, action: str) -> str:
    """A 500 message without the host path that ``str(OSError)`` would include."""
    reason = exc.strerror or exc.__class__.__name__
    return f"Could not {action}: {reason}."


def _file_version(filepath: str) -> str:
    """Opaque version of a file on disk (hash of its bytes), for save-conflict checks."""
    with open(filepath, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


@app.get("/api/file-content")
def get_file_content(filename: str):
    """Return a script's code with its parsed scenes and timeline."""
    filename, filepath = _script_path(filename)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="Python script not found.")
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        version = _file_version(filepath)
    except OSError as e:
        raise HTTPException(status_code=500, detail=_os_error_detail(e, "read the script"))
    return {"filename": filename, "code": content, "version": version, **_parsed(content)}


class ParseRequest(BaseModel):
    code: str


@app.post("/api/parse-code")
def parse_code(req: ParseRequest):
    """Parse code without writing it to disk."""
    _ensure_code_within_limit(req.code)
    return {"success": True, **_parsed(req.code)}


class SaveRequest(BaseModel):
    filename: str
    code: str
    # The version the editor loaded (from /api/file-content or the last save).
    # When given, the save only goes through if the file still exists and is
    # unchanged on disk, so two tabs can't silently overwrite each other and a
    # save can't recreate a file that was renamed or deleted elsewhere.
    base_version: Optional[str] = None
    # New-file dialogs: never overwrite a file that already exists (e.g. created in another tab).
    create_only: bool = False


@app.post("/api/save")
def save_file(req: SaveRequest):
    """Write a script and return its parsed scenes and new version."""
    _ensure_code_within_limit(req.code)
    filename, filepath = _new_script_path(req.filename)
    if req.base_version is not None:
        # 412 (not 409, which means a case-only name clash here) when the file
        # changed since the editor loaded it; 404 when it is gone.
        if not os.path.isfile(filepath):
            raise HTTPException(status_code=404, detail="This file was renamed or deleted outside this tab.")
        try:
            current = _file_version(filepath)
        except OSError as e:
            raise HTTPException(status_code=500, detail=_os_error_detail(e, "read the script"))
        if current != req.base_version:
            raise HTTPException(status_code=412, detail="This file was changed outside this tab since you opened it.")
    if req.create_only and os.path.exists(filepath):
        raise HTTPException(status_code=409, detail=f"{filename} already exists.")
    _reject_case_collision(WORKSPACE_DIR, filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(req.code)
        version = _file_version(filepath)
    except OSError as e:
        raise HTTPException(status_code=500, detail=_os_error_detail(e, "save the script"))
    return {"success": True, "filename": filename, "message": "File saved.", "version": version, **_parsed(req.code)}


class RenameRequest(BaseModel):
    old_name: str
    new_name: str


@app.post("/api/rename")
def rename_file(req: RenameRequest):
    """Rename a workspace script."""
    old_name, old_path = _script_path(req.old_name)
    new_name, new_path = _script_path(to_script_name(req.new_name), new=True)

    if not os.path.exists(old_path):
        raise HTTPException(status_code=404, detail="Source file not found.")

    is_case_only = os.path.normcase(old_path) == os.path.normcase(new_path)
    if os.path.exists(new_path) and not is_case_only:
        raise HTTPException(status_code=400, detail="A file with the target name already exists.")
    clash = find_case_insensitive_match(WORKSPACE_DIR, new_name)
    if clash and clash != old_name:
        _reject_case_collision(WORKSPACE_DIR, new_name)

    try:
        if is_case_only and old_name != new_name:
            # Case-insensitive filesystems need a hop through a temporary name.
            temp_path = safe_join(WORKSPACE_DIR, f"__tmp_rename_{uuid.uuid4().hex[:8]}_{old_name}")
            os.rename(old_path, temp_path)
            os.rename(temp_path, new_path)
        else:
            os.rename(old_path, new_path)
    except OSError as e:
        raise HTTPException(status_code=500, detail=_os_error_detail(e, "rename the script"))

    return {"success": True, "old_name": old_name, "new_name": new_name, "message": f"Renamed {old_name} to {new_name}."}


@app.delete("/api/scripts")
def delete_script(filename: str):
    """Delete a workspace script."""
    filename, filepath = _script_path(filename)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="Python script not found.")
    try:
        os.remove(filepath)
    except OSError as e:
        raise HTTPException(status_code=500, detail=_os_error_detail(e, "delete the script"))
    return {"success": True, "filename": filename}


@app.post("/api/upload-asset")
async def upload_asset(file: UploadFile = File(...), overwrite: bool = False):
    """Store an uploaded asset (image, audio, font) in workspace/assets/.

    An existing file is left untouched unless ``overwrite`` is true. The upload
    is written to a temporary name and moved into place only after it succeeds,
    so a rejected upload cannot delete the file it was replacing.
    """
    try:
        filename = validate_new_filename(nfc_filename(file.filename))
        dest_path = safe_join(ASSETS_DIR, filename)
    except UnsafePathError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid asset filename: {exc}")

    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_ASSET_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported asset type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_ASSET_EXTENSIONS))}",
        )

    _reject_case_collision(ASSETS_DIR, filename)
    existed = os.path.exists(dest_path)
    if existed and not overwrite:
        raise HTTPException(
            status_code=409,
            detail=(
                f"An asset named '{filename}' already exists. "
                "Confirm to replace it (send the upload again with overwrite=true)."
            ),
        )

    partial_path = f"{dest_path}.uploading-{uuid.uuid4().hex}"

    def discard_partial():
        try:
            if os.path.exists(partial_path):
                os.remove(partial_path)
        except OSError:
            pass

    try:
        size = 0
        with open(partial_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_ASSET_SIZE_BYTES:
                    break
                buffer.write(chunk)
        if size > MAX_ASSET_SIZE_BYTES:
            discard_partial()
            raise HTTPException(status_code=413, detail="File size exceeds maximum allowed size (50MB).")
        os.replace(partial_path, dest_path)
    except HTTPException:
        raise
    except OSError as e:
        discard_partial()
        raise HTTPException(status_code=500, detail=_os_error_detail(e, "store the upload"))
    except Exception:
        discard_partial()
        raise HTTPException(status_code=500, detail="Could not store the upload.")

    return {"success": True, "filename": filename, "url": f"/assets/{quote(filename)}", "replaced": existed}


@app.delete("/api/assets")
def delete_asset(filename: str):
    """Delete an uploaded asset."""
    try:
        filename = safe_basename(filename)
        filepath = safe_join(ASSETS_DIR, filename)
    except UnsafePathError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid asset filename: {exc}")
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="Asset not found.")
    try:
        os.remove(filepath)
    except OSError as e:
        raise HTTPException(status_code=500, detail=_os_error_detail(e, "delete the asset"))
    return {"success": True, "filename": filename}


def _media_request_path(path: str) -> str:
    """Normalize a client-supplied media path to be relative to MEDIA_DIR."""
    clean = path.strip().replace("\\", "/").lstrip("/")
    return clean[len("media/"):] if clean.startswith("media/") else clean


def _is_temp_media_relpath(rel_path: str) -> bool:
    """True if *rel_path* (relative to MEDIA_DIR) lies under a _temp_run_* directory.

    Parent segments (``..``) are rejected before they can be normalized away.
    The temp-run name has to be a directory, not the file itself.
    """
    raw = rel_path.replace("\\", "/")
    parts = [part for part in raw.split("/") if part and part != "."]
    if not parts or any(part == ".." for part in parts):
        return False
    return any(part.startswith(TEMP_PREFIX) for part in parts[:-1])


def _temp_run_directory(abs_path: str) -> Optional[str]:
    """The ``_temp_run_*`` directory that actually contains *abs_path*, if any."""
    media_root = os.path.normcase(os.path.abspath(MEDIA_DIR))
    directory = os.path.dirname(os.path.abspath(abs_path))
    while True:
        normalized = os.path.normcase(os.path.abspath(directory))
        if normalized == media_root:
            return None
        if not normalized.startswith(media_root + os.sep):
            return None
        if os.path.basename(directory).startswith(TEMP_PREFIX):
            return directory
        parent = os.path.dirname(directory)
        if parent == directory:
            return None
        directory = parent


def _cross_site_get(request: Request) -> bool:
    """True for browser loads that are not this app's own fetch (an ``<img>`` tag, for example)."""
    dest = (request.headers.get("sec-fetch-dest") or "").lower()
    site = (request.headers.get("sec-fetch-site") or "").lower()
    if dest in {"image", "script", "object", "embed", "style"}:
        return True
    return site in {"cross-site", "same-site"}


def _prune_empty_dirs(start_dir: str, stop_dir: str) -> None:
    current = start_dir
    while os.path.normcase(os.path.abspath(current)) != os.path.normcase(os.path.abspath(stop_dir)):
        try:
            os.rmdir(current)
        except OSError:
            return
        current = os.path.dirname(current)


@app.delete("/api/media")
def delete_media(path: str):
    """Delete a rendered video or image (path relative to workspace/media)."""
    rel_path = _media_request_path(path)
    top = rel_path.split("/", 1)[0]
    if ".." in rel_path.split("/"):
        # Check the folder after resolving, not before: videos/../texts/x.png must not pass.
        raise HTTPException(status_code=400, detail="Invalid media path.")
    if top not in MEDIA_SUBDIRS or not rel_path.lower().endswith(OUTPUT_EXTENSIONS):
        raise HTTPException(status_code=400, detail="Only rendered videos and images can be deleted.")
    try:
        abs_path = safe_join(MEDIA_DIR, rel_path)
    except UnsafePathError:
        raise HTTPException(status_code=400, detail="Invalid media path.")
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="Media file not found.")

    try:
        os.remove(abs_path)
    except OSError as e:
        raise HTTPException(status_code=500, detail=_os_error_detail(e, "delete the render"))

    parent = os.path.dirname(abs_path)
    if top == "videos":
        # Drop the scene's cached animation chunks along with the final video.
        scene = os.path.splitext(os.path.basename(abs_path))[0]
        shutil.rmtree(os.path.join(parent, "partial_movie_files", scene), ignore_errors=True)
        _prune_empty_dirs(os.path.join(parent, "partial_movie_files"), os.path.join(MEDIA_DIR, top))
    _prune_empty_dirs(parent, os.path.join(MEDIA_DIR, top))
    return {"success": True, "path": rel_path}


@app.get("/api/download-temp")
def download_temp(path: str, request: Request, background_tasks: BackgroundTasks):
    """Serve a download-only render once, then delete that temp directory.

    The resolved file has to sit inside a real ``_temp_run_*`` directory.
    A path that merely mentions that prefix, or climbs out of it with ``..``,
    is refused. Cross-site GET loads (an ``<img>`` on another page) are refused
    too, because this endpoint deletes the file it serves.
    """
    if _cross_site_get(request):
        raise HTTPException(status_code=403, detail="Cross-site downloads are not allowed.")

    clean_path = _media_request_path(path)

    if not _is_temp_media_relpath(clean_path):
        raise HTTPException(
            status_code=400,
            detail="Only temporary render outputs (_temp_run_*) can be downloaded via this endpoint.",
        )

    try:
        abs_path = safe_join(MEDIA_DIR, clean_path)
    except UnsafePathError:
        raise HTTPException(status_code=400, detail="Access denied")

    temp_dir = _temp_run_directory(abs_path)
    if temp_dir is None:
        raise HTTPException(status_code=400, detail="Access denied")

    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="File not found")

    media_type = mimetypes.guess_type(abs_path)[0] or "video/mp4"

    def remove_temp_output():
        # Delete only the temp run that contains the file. Never the file on its own:
        # a path that resolved outside a temp directory must not be removed.
        if _temp_run_directory(abs_path) == temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)

    background_tasks.add_task(remove_temp_output)
    return FileResponse(abs_path, media_type=media_type, filename=os.path.basename(abs_path))


# --------------------------------------------------------------------------- #
# Dependency installers (Windows winget / pip)
# --------------------------------------------------------------------------- #


def _installers_allowed() -> Optional[str]:
    """Return an error message if package-install endpoints must be refused, else None."""
    if os.environ.get("RUNNING_IN_DOCKER") == "true" or os.environ.get("RENDER") == "true":
        return "Package installation endpoints are disabled in container/cloud deployments."
    if os.environ.get("MANIM_ALLOW_INSTALLS", "").lower() in ("0", "false", "no"):
        return "Package installation endpoints are disabled by MANIM_ALLOW_INSTALLS."
    return None


def _require_installers_allowed() -> None:
    blocked = _installers_allowed()
    if blocked:
        raise HTTPException(status_code=403, detail=blocked)


def _find_winget() -> str:
    winget_path = shutil.which("winget")
    if winget_path:
        return winget_path
    fallback = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\winget.exe")
    if os.path.exists(fallback):
        return fallback
    raise HTTPException(status_code=400, detail="winget package manager is not installed on this system.")


def _start_background(cmd: List[str]) -> None:
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _winget_install(package_id: str, label: str) -> dict:
    _require_installers_allowed()
    _start_background(
        [
            _find_winget(),
            "install",
            "--id",
            package_id,
            "--silent",
            "--accept-source-agreements",
            "--accept-package-agreements",
            "--scope",
            "user",
        ]
    )
    return {
        "success": True,
        "message": f"{label} is installing in the background for your user account (no admin prompt).",
    }


@app.post("/api/install-latex")
def install_latex():
    """Install MiKTeX with winget (Windows)."""
    return _winget_install("MiKTeX.MiKTeX", "MiKTeX")


@app.post("/api/install-ffmpeg")
def install_ffmpeg():
    """Install FFmpeg with winget (Windows)."""
    return _winget_install("Gyan.FFmpeg", "FFmpeg")


@app.post("/api/install-manim")
def install_manim():
    """pip-install Manim CE into the Python environment running this server."""
    _require_installers_allowed()
    if not sys.executable:
        raise HTTPException(status_code=400, detail="Python executable could not be identified.")
    _start_background([sys.executable, "-m", "pip", "install", "manim"])
    return {"success": True, "message": "Manim CE is installing in the background via pip."}


# --------------------------------------------------------------------------- #
# Render WebSocket
# --------------------------------------------------------------------------- #


def _manim_command(binaries: dict) -> Optional[List[str]]:
    command = binaries.get("manim_command")
    if command:
        return list(command)
    path = binaries.get("manim")
    if path and path != "Not Found":
        return [path]
    return None


def _relocate_temp_output(abs_path: str, temp_stem: str, target_stem: str) -> Optional[str]:
    """Move a render of a scratch script into the media folder of the script it came from."""
    try:
        rel_parts = os.path.relpath(abs_path, MEDIA_DIR).replace("\\", "/").split("/")
        if temp_stem not in rel_parts:
            return None
        dest = safe_join(MEDIA_DIR, *[target_stem if part == temp_stem else part for part in rel_parts])
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        os.replace(abs_path, dest)
        return dest
    except (OSError, UnsafePathError, ValueError):
        return None


# Temp stems of renders still running; the stale-download sweep never touches these.
_active_temp_stems: set = set()


def _newest_mtime(path: str) -> float:
    newest = os.path.getmtime(path)
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            try:
                newest = max(newest, os.path.getmtime(os.path.join(root, name)))
            except OSError:
                pass
    return newest


def _sweep_stale_temp_downloads(ttl: Optional[float] = None) -> None:
    """Remove download-only outputs whose one-time link was never fetched.

    Only ``media/*/_temp_run_*`` directories untouched for *ttl* seconds are removed,
    and never one that belongs to a render that is still running.
    """
    ttl = TEMP_DOWNLOAD_TTL_SECONDS if ttl is None else ttl
    cutoff = time.time() - ttl
    for sub in MEDIA_SUBDIRS:
        root = os.path.join(MEDIA_DIR, sub)
        try:
            entries = list(os.scandir(root))
        except OSError:
            continue
        for entry in entries:
            if not entry.name.startswith(TEMP_PREFIX) or entry.name in _active_temp_stems:
                continue
            try:
                if entry.is_dir(follow_symlinks=False) and _newest_mtime(entry.path) < cutoff:
                    shutil.rmtree(entry.path, ignore_errors=True)
            except OSError:
                pass


def _remove_temp_media(temp_stem: str) -> None:
    for sub in MEDIA_SUBDIRS:
        shutil.rmtree(os.path.join(MEDIA_DIR, sub, temp_stem), ignore_errors=True)


def _file_ready_event(abs_path: str, rel_path: str) -> dict:
    parts = rel_path.split("/")
    return {
        "type": "file_ready",
        "rel_path": rel_path,
        "url": "/" + "/".join(quote(part) for part in parts),
        "filename": os.path.basename(abs_path),
        "kind": output_kind(abs_path),
    }


class _RenderRequestError(ValueError):
    pass


def _validate_start_message(message: dict) -> dict:
    filename = message.get("filename")
    scene_name = message.get("scene")
    quality = message.get("quality", "m")
    code_content = message.get("code")

    if not filename or not scene_name:
        raise _RenderRequestError("Render requests require both a filename and a scene name.")
    if not isinstance(scene_name, str) or not scene_name.isidentifier():
        raise _RenderRequestError("Scene name must be a valid Python identifier.")
    if not isinstance(quality, str) or quality not in ALLOWED_QUALITIES:
        raise _RenderRequestError("Quality must be one of: l, m, h, k.")
    try:
        filename = validate_new_filename(filename, required_suffix=".py", forbid_temp_prefix=True)
    except UnsafePathError as exc:
        raise _RenderRequestError(_bad_script_name_detail(filename, exc))
    if code_content is not None:
        if not isinstance(code_content, str):
            raise _RenderRequestError("Code payload must be a string.")
        if len(code_content.encode("utf-8")) > MAX_CODE_BYTES:
            raise _RenderRequestError(f"Code payload exceeds maximum size ({MAX_CODE_BYTES} bytes).")

    return {
        "filename": filename,
        "scene": scene_name,
        "quality": quality,
        "use_opengl": _coerce_flag(message.get("use_opengl"), "use_opengl"),
        "download_only": _coerce_flag(message.get("download_only"), "download_only"),
        "code": code_content,
    }


_TRUE_STRINGS = frozenset({"true", "1", "yes", "on"})
_FALSE_STRINGS = frozenset({"false", "0", "no", "off", ""})


def _coerce_flag(value, field: str) -> bool:
    """Read a boolean flag from JSON. ``"false"`` and ``"0"`` are False; junk is rejected."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUE_STRINGS:
            return True
        if lowered in _FALSE_STRINGS:
            return False
    raise _RenderRequestError(f"{field} must be true or false.")


class _RenderState:
    """One accepted ``start`` on a render socket, from validation to its ``result``."""

    __slots__ = ("render_id", "task", "phase", "result_sent")

    def __init__(self, render_id):
        self.render_id = render_id
        self.task: Optional[asyncio.Task] = None
        # "pending" (task not started yet), "preparing" (scratch copy, pre-checks),
        # "queued" (waiting for a render slot), "rendering" (Manim running), or
        # "finishing" (Manim exited; output, cleanup, and the result being sent).
        # Only the first three are cancelled outright; a finishing render is
        # never interrupted, so its result cannot be lost mid-send.
        self.phase = "pending"
        self.result_sent = False


# Renders waiting for a slot, oldest first, across all sockets. Used for the
# queue position reported in "queued" events.
_render_waiters: List[_RenderState] = []


def _queue_position(state: _RenderState) -> int:
    try:
        return _render_waiters.index(state) + 1
    except ValueError:
        return 0


@app.websocket("/api/render")
async def websocket_render(websocket: WebSocket):
    """Run renders over a WebSocket and stream logs, progress, and results.

    Client messages: ``{"type": "start", "id", "filename", "scene", "quality",
    "use_opengl", "download_only", "code"?}`` and ``{"type": "cancel", "id"?}``.
    Every event produced by a render carries the ``render_id`` echoed from
    ``id`` so clients can ignore events from a render they already abandoned.
    Every accepted or rejected ``start`` gets exactly one ``result``, including
    a start that is cancelled or replaced before it begins.

    While a render waits for a free slot the server sends
    ``{"type": "queued", "render_id", "position", "message"}`` (position 1 is
    next), followed by the legacy ``info`` line for older clients, and
    ``{"type": "started", "render_id", "waited"}`` once it leaves the queue.
    Each connection gets its own executor so clients never interfere.
    """
    if not _request_allowed(websocket.headers, _peer_host(websocket.client)):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    current: Optional[_RenderState] = None
    conn_executor = ManimExecutor(WORKSPACE_DIR)

    async def send(payload: dict) -> bool:
        try:
            await websocket.send_json(payload)
            return True
        except (WebSocketDisconnect, RuntimeError):
            return False

    async def send_result(state: _RenderState, result: dict) -> None:
        if state.result_sent:
            return
        state.result_sent = True
        await send(
            {
                "type": "result",
                "render_id": state.render_id,
                "success": bool(result.get("success")),
                "status": result.get("status", "unknown"),
                "details": result,
            }
        )

    async def settle(state: _RenderState, reason: str) -> None:
        """Wait for a stopped render's task, and report it if it never could."""
        if state.task is not None:
            try:
                await state.task
            except (asyncio.CancelledError, Exception):
                pass
        # A task cancelled before its first step never runs its own finally block.
        await send_result(state, {"success": False, "status": "cancelled", "reason": reason})

    async def stop_render(state: _RenderState, reason: str) -> None:
        task = state.task
        if task is not None and not task.done():
            if state.phase == "rendering":
                # Stops Manim, or stops it as soon as it has been spawned. The task
                # then finishes on its own and reports "cancelled".
                await conn_executor.cancel()
                _done, pending = await asyncio.wait({task}, timeout=STOP_GRACE_SECONDS)
                if pending:
                    task.cancel()
            elif state.phase in ("pending", "preparing", "queued"):
                # Not started, preparing, or waiting for a slot: nothing to kill yet.
                task.cancel()
        await settle(state, reason)

    async def stop_current_render(reason: str = "cancelled") -> None:
        nonlocal current
        state, current = current, None
        if state is not None:
            await stop_render(state, reason)

    async def run_render(state: _RenderState, request: dict, manim_command: List[str]):
        render_id = state.render_id
        filename = request["filename"]
        download_only = request["download_only"]
        target_stem = os.path.splitext(filename)[0]
        script_name = filename
        temp_filepath: Optional[str] = None
        temp_stem: Optional[str] = None
        relocate = False
        held_output: List[str] = []
        result: dict = {"success": False, "status": "error"}

        async def log_callback(event: dict):
            outbound = dict(event)
            abs_path = outbound.pop("abs_path", None)  # never leak host paths to the client
            if temp_stem and isinstance(outbound.get("message"), str):
                # Show the user's filename instead of the scratch copy in tracebacks. Media
                # folder names are rewritten too when the output is moved there afterwards.
                original = outbound["message"]
                message = original.replace(script_name, filename)
                message = message.replace(temp_stem, target_stem) if relocate else message
                outbound["message"] = keep_box_width(original, message)

            if outbound.get("type") == "file_ready" and abs_path:
                if relocate:
                    held_output.append(abs_path)  # announced after it has been moved
                    return
                if download_only:
                    rel = outbound.get("rel_path", "")
                    path_param = rel[len("media/"):] if rel.startswith("media/") else rel
                    outbound["rel_path"] = f"api/download-temp?path={quote(path_param)}"
                    outbound["url"] = "/" + outbound["rel_path"]
                    outbound["is_temp_download"] = True
                else:
                    outbound.update(_file_ready_event(abs_path, outbound.get("rel_path", "")))

            outbound["render_id"] = render_id
            if not await send(outbound):
                await conn_executor.cancel()

        state.phase = "preparing"
        try:
            # Unsaved code and download-only renders run from a scratch copy so that
            # their output lands under media/*/_temp_run_*.
            code_content = request["code"]
            if download_only or code_content is not None:
                if code_content is None:
                    src_path = os.path.join(WORKSPACE_DIR, filename)
                    if not os.path.isfile(src_path):
                        await send({"type": "error", "render_id": render_id, "message": "Python script not found."})
                        result = {"success": False, "status": "rejected"}
                        return
                    with open(src_path, "r", encoding="utf-8", errors="replace") as f:
                        code_content = f.read()
                script_name = f"{TEMP_PREFIX}{uuid.uuid4().hex[:8]}.py"
                temp_stem = os.path.splitext(script_name)[0]
                _active_temp_stems.add(temp_stem)
                relocate = not download_only
                temp_filepath = os.path.join(WORKSPACE_DIR, script_name)
                with open(temp_filepath, "w", encoding="utf-8") as f:
                    f.write(code_content)

            checked = code_content
            if checked is None:
                src_path = os.path.join(WORKSPACE_DIR, filename)
                if not os.path.isfile(src_path):
                    await send({"type": "error", "render_id": render_id, "message": "Python script not found."})
                    result = {"success": False, "status": "rejected"}
                    return
                with open(src_path, "r", encoding="utf-8", errors="replace") as f:
                    checked = f.read()
            blocked = _render_block_reason(checked, request["scene"])
            if blocked:
                await send({"type": "error", "render_id": render_id, "message": blocked})
                result = {"success": False, "status": "rejected"}
                return
            warning = _render_scene_warning(checked, request["scene"])
            if warning:
                await send({"type": "info", "render_id": render_id, "message": warning})

            state.phase = "queued"
            slots = _render_semaphore()
            waited = slots.locked()
            if waited:
                _render_waiters.append(state)
                try:
                    position = _queue_position(state)
                    message = f"Waiting for another render to finish… (position {position} in queue)"
                    await send({"type": "queued", "render_id": render_id, "position": position, "message": message})
                    await send({"type": "info", "render_id": render_id, "message": message})
                    await slots.acquire()
                finally:
                    _render_waiters.remove(state)
            else:
                await slots.acquire()
            try:
                if waited:
                    await send({"type": "started", "render_id": render_id, "waited": True})
                state.phase = "rendering"
                result = await conn_executor.execute(
                    manim_path=manim_command,
                    script_name=script_name,
                    scene_name=request["scene"],
                    quality=request["quality"],
                    use_opengl=request["use_opengl"],
                    log_callback=log_callback,
                )
            finally:
                slots.release()
            state.phase = "finishing"
            if relocate and held_output and result.get("success"):
                moved = await asyncio.to_thread(_relocate_temp_output, held_output[-1], temp_stem, target_stem)
                final_path = moved or held_output[-1]
                await send({**_file_ready_event(final_path, media_rel_path(final_path)), "render_id": render_id})
        except asyncio.CancelledError:
            if state.phase == "rendering":
                await conn_executor.cancel()
            result = {"success": False, "status": "cancelled"}
            raise
        except Exception as e:
            result = {"success": False, "status": "error", "error": str(e)}
            await send({"type": "error", "render_id": render_id, "message": f"Render execution error: {e}"})
        finally:
            state.phase = "finishing"
            # Clean up before the last await, so a cancellation during the send can't skip it.
            if temp_filepath:
                try:
                    os.remove(temp_filepath)
                except OSError:
                    pass
            if relocate and temp_stem:
                _remove_temp_media(temp_stem)
            _active_temp_stems.discard(temp_stem)
            await send_result(state, result)

    async def reject_oversized(data: str) -> None:
        render_id, is_start = None, False
        try:
            parsed = json.loads(data)
            if isinstance(parsed, dict):
                render_id, is_start = parsed.get("id"), parsed.get("type") == "start"
        except (ValueError, RecursionError):
            pass
        await send({
            "type": "error",
            "render_id": render_id,
            "message": _body_too_large(),
        })
        if is_start:
            await send({"type": "result", "render_id": render_id, "success": False, "status": "rejected"})

    try:
        while True:
            data = await websocket.receive_text()
            if len(data.encode("utf-8")) > MAX_REQUEST_BODY_BYTES:
                await reject_oversized(data)
                continue
            try:
                message = json.loads(data)
            except (ValueError, RecursionError):
                await send({"type": "error", "message": "Invalid JSON message."})
                continue
            if not isinstance(message, dict):
                await send({"type": "error", "message": "Message payload must be a JSON object."})
                continue

            msg_type = message.get("type")
            if msg_type == "start":
                render_id = message.get("id")
                # The previous render (if any) gets its own "cancelled" result first.
                await stop_current_render("superseded")
                try:
                    request = _validate_start_message(message)
                    # PATH lookups can be slow (network drives); keep them off the event loop.
                    manim_command = _manim_command(await asyncio.to_thread(get_binary_paths))
                    if not manim_command:
                        raise _RenderRequestError(
                            "Manim executable not found. Install Manim CE (pip install manim) and restart."
                        )
                except _RenderRequestError as exc:
                    # Every start gets exactly one result, even when it is rejected.
                    await send({"type": "error", "render_id": render_id, "message": str(exc)})
                    await send({"type": "result", "render_id": render_id, "success": False, "status": "rejected"})
                    continue

                state = _RenderState(render_id)
                state.task = asyncio.create_task(run_render(state, request, manim_command))
                current = state

            elif msg_type == "cancel":
                state = current
                if state is None or state.task is None or state.task.done():
                    continue
                if "id" in message and message.get("id") != state.render_id:
                    # A cancel for a render that is no longer current must not stop this one.
                    await send({
                        "type": "info",
                        "render_id": message.get("id"),
                        "message": "That render is not running.",
                    })
                    continue
                if state.phase == "finishing":
                    # Manim already finished; let the output and result through.
                    continue
                await send({"type": "info", "render_id": state.render_id, "message": "Stopping render..."})
                current = None
                await stop_render(state, "cancelled")

    except WebSocketDisconnect:
        await stop_current_render("disconnected")
    except Exception as e:
        await stop_current_render("error")
        await send({"type": "error", "message": f"Server WebSocket error: {e}"})


# Serve the built frontend (index.html + static files). /assets is handled above.
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:

    @app.get("/")
    def read_root():
        return read_status()


def _cli_address(argv=None) -> tuple:
    """Host and port for ``python backend/main.py`` / ``npm run backend``.

    ``--host``/``--port`` win, then MANIM_HOST/MANIM_PORT, then 127.0.0.1:8000.
    """
    import argparse

    parser = argparse.ArgumentParser(description="Run the Manim Composer API (no frontend build).")
    parser.add_argument("--host", default=os.environ.get("MANIM_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MANIM_PORT", "8000")))
    args = parser.parse_args(argv)
    return args.host, args.port


if __name__ == "__main__":
    import uvicorn

    _host, _port = _cli_address()
    uvicorn.run(app, host=_host, port=_port)
