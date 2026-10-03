"""FastAPI backend for Manim Composer: workspace files, diagnostics, and live renders."""

import asyncio
import json
import mimetypes
import os
import platform
import shutil
import subprocess
import sys
import uuid
from typing import List, Optional
from urllib.parse import quote

# Ensure backend directory is in python search path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from diagnostics import get_binary_paths, get_cached_profile, write_manim_config_file
from executor import OUTPUT_EXTENSIONS, ManimExecutor, media_rel_path, output_kind
from origins import is_host_allowed, is_origin_allowed
from scene_parser import get_scene_animations, get_scenes_from_code
from workspace_paths import UnsafePathError, safe_basename, safe_join
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


app = FastAPI(title="Manim Composer API", version=APP_VERSION)


def _request_allowed(headers) -> bool:
    host = headers.get("host")
    return is_host_allowed(host) and is_origin_allowed(headers.get("origin"), host)


@app.middleware("http")
async def reject_untrusted_requests(request: Request, call_next):
    if not _request_allowed(request.headers):
        return JSONResponse({"detail": "Request origin or host not allowed."}, status_code=403)
    return await call_next(request)


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


_sweep_temp_renders()
write_manim_config_file(WORKSPACE_DIR, get_cached_profile())

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
    return FileResponse(user_file)


def _parsed(code: str) -> dict:
    return {"scenes": get_scenes_from_code(code), "animations": get_scene_animations(code)}


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
    scripts = _list_scripts()
    if not scripts:
        # Never leave the editor empty: seed the workspace with a starter script.
        with open(os.path.join(WORKSPACE_DIR, DEFAULT_SCRIPT_NAME), "w", encoding="utf-8") as f:
            f.write(DEFAULT_SCRIPT)
        scripts = _list_scripts()
    return {"scripts": scripts, "assets": _list_assets(), "media": _list_media()}


def _script_path(filename: str) -> tuple:
    try:
        name = safe_basename(filename, required_suffix=".py")
        return name, safe_join(WORKSPACE_DIR, name)
    except UnsafePathError:
        raise HTTPException(status_code=400, detail="Invalid script filename.")


@app.get("/api/file-content")
def get_file_content(filename: str):
    """Return a script's code with its parsed scenes and timeline."""
    filename, filepath = _script_path(filename)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="Python script not found.")
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")
    return {"filename": filename, "code": content, **_parsed(content)}


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


@app.post("/api/save")
def save_file(req: SaveRequest):
    """Write a script and return its parsed scenes."""
    _ensure_code_within_limit(req.code)
    filename = req.filename if req.filename.endswith(".py") else f"{req.filename}.py"
    filename, filepath = _script_path(filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(req.code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"success": True, "filename": filename, "message": "File saved.", **_parsed(req.code)}


class RenameRequest(BaseModel):
    old_name: str
    new_name: str


@app.post("/api/rename")
def rename_file(req: RenameRequest):
    """Rename a workspace script."""
    try:
        old_name = safe_basename(req.old_name, required_suffix=".py")
        new_name = safe_basename(req.new_name, required_suffix=".py")
        old_path = safe_join(WORKSPACE_DIR, old_name)
        new_path = safe_join(WORKSPACE_DIR, new_name)
    except UnsafePathError:
        raise HTTPException(status_code=400, detail="Only python (.py) scripts in the workspace can be renamed.")

    if not os.path.exists(old_path):
        raise HTTPException(status_code=404, detail="Source file not found.")

    is_case_only = os.path.normcase(old_path) == os.path.normcase(new_path)
    if os.path.exists(new_path) and not is_case_only:
        raise HTTPException(status_code=400, detail="A file with the target name already exists.")

    try:
        if is_case_only and old_name != new_name:
            # Case-insensitive filesystems need a hop through a temporary name.
            temp_path = safe_join(WORKSPACE_DIR, f"__tmp_rename_{uuid.uuid4().hex[:8]}_{old_name}")
            os.rename(old_path, temp_path)
            os.rename(temp_path, new_path)
        else:
            os.rename(old_path, new_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))
    return {"success": True, "filename": filename}


@app.post("/api/upload-asset")
async def upload_asset(file: UploadFile = File(...)):
    """Store an uploaded asset (image, audio, font) in workspace/assets/."""
    try:
        filename = safe_basename(file.filename)
        dest_path = safe_join(ASSETS_DIR, filename)
    except UnsafePathError:
        raise HTTPException(status_code=400, detail="Uploaded file must include a valid filename.")

    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_ASSET_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported asset type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_ASSET_EXTENSIONS))}",
        )

    def discard_partial():
        try:
            if os.path.exists(dest_path):
                os.remove(dest_path)
        except OSError:
            pass

    try:
        size = 0
        with open(dest_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_ASSET_SIZE_BYTES:
                    break
                buffer.write(chunk)
        if size > MAX_ASSET_SIZE_BYTES:
            discard_partial()
            raise HTTPException(status_code=413, detail="File size exceeds maximum allowed size (50MB).")
    except HTTPException:
        raise
    except Exception as e:
        discard_partial()
        raise HTTPException(status_code=500, detail=str(e))

    return {"success": True, "filename": filename, "url": f"/assets/{quote(filename)}"}


@app.delete("/api/assets")
def delete_asset(filename: str):
    """Delete an uploaded asset."""
    try:
        filename = safe_basename(filename)
        filepath = safe_join(ASSETS_DIR, filename)
    except UnsafePathError:
        raise HTTPException(status_code=400, detail="Invalid asset filename.")
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="Asset not found.")
    try:
        os.remove(filepath)
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"success": True, "filename": filename}


def _media_request_path(path: str) -> str:
    """Normalize a client-supplied media path to be relative to MEDIA_DIR."""
    clean = path.strip().replace("\\", "/").lstrip("/")
    return clean[len("media/"):] if clean.startswith("media/") else clean


def _is_temp_media_relpath(rel_path: str) -> bool:
    """True if *rel_path* (relative to MEDIA_DIR) lies under a _temp_run_* directory."""
    parts = [p for p in rel_path.replace("\\", "/").split("/") if p and p != "."]
    return any(part.startswith(TEMP_PREFIX) for part in parts)


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
        raise HTTPException(status_code=500, detail=str(e))

    parent = os.path.dirname(abs_path)
    if top == "videos":
        # Drop the scene's cached animation chunks along with the final video.
        scene = os.path.splitext(os.path.basename(abs_path))[0]
        shutil.rmtree(os.path.join(parent, "partial_movie_files", scene), ignore_errors=True)
        _prune_empty_dirs(os.path.join(parent, "partial_movie_files"), os.path.join(MEDIA_DIR, top))
    _prune_empty_dirs(parent, os.path.join(MEDIA_DIR, top))
    return {"success": True, "path": rel_path}


@app.get("/api/download-temp")
def download_temp(path: str, background_tasks: BackgroundTasks):
    """Serve a download-only render once, then delete it.

    Only paths under a ``_temp_run_*`` directory are accepted, so permanent
    renders can never be deleted through this endpoint.
    """
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

    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="File not found")

    media_type = mimetypes.guess_type(abs_path)[0] or "video/mp4"

    def remove_temp_output():
        # Remove the whole _temp_run_* tree, never a non-temp parent.
        current = os.path.dirname(abs_path)
        media_root = os.path.normcase(os.path.abspath(MEDIA_DIR))
        while os.path.normcase(os.path.abspath(current)) != media_root:
            if os.path.basename(current).startswith(TEMP_PREFIX):
                shutil.rmtree(current, ignore_errors=True)
                return
            current = os.path.dirname(current)
        try:
            os.remove(abs_path)
        except OSError:
            pass

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
        filename = safe_basename(filename, required_suffix=".py")
    except UnsafePathError:
        raise _RenderRequestError("Invalid script filename.")
    if code_content is not None:
        if not isinstance(code_content, str):
            raise _RenderRequestError("Code payload must be a string.")
        if len(code_content.encode("utf-8")) > MAX_CODE_BYTES:
            raise _RenderRequestError(f"Code payload exceeds maximum size ({MAX_CODE_BYTES} bytes).")

    return {
        "filename": filename,
        "scene": scene_name,
        "quality": quality,
        "use_opengl": bool(message.get("use_opengl", False)),
        "download_only": bool(message.get("download_only", False)),
        "code": code_content,
    }


@app.websocket("/api/render")
async def websocket_render(websocket: WebSocket):
    """Run renders over a WebSocket and stream logs, progress, and results.

    Client messages: ``{"type": "start", "id", "filename", "scene", "quality",
    "use_opengl", "download_only", "code"?}`` and ``{"type": "cancel"}``.
    Every event produced by a render carries the ``render_id`` echoed from
    ``id`` so clients can ignore events from a render they already abandoned.
    Each connection gets its own executor so clients never interfere.
    """
    if not _request_allowed(websocket.headers):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    current_render_task: Optional[asyncio.Task] = None
    conn_executor = ManimExecutor(WORKSPACE_DIR)

    async def send(payload: dict) -> bool:
        try:
            await websocket.send_json(payload)
            return True
        except (WebSocketDisconnect, RuntimeError):
            return False

    async def stop_current_render():
        nonlocal current_render_task
        await conn_executor.cancel()
        if current_render_task and not current_render_task.done():
            current_render_task.cancel()
            try:
                await current_render_task
            except (asyncio.CancelledError, Exception):
                pass
        current_render_task = None

    # What the current render is doing: "preparing" (writing the scratch copy),
    # "rendering" (Manim running), or "finishing" (moving/announcing the output).
    phase: dict = {"value": None}

    async def run_render(request: dict, render_id, manim_command: List[str]):
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
                message = outbound["message"].replace(script_name, filename)
                outbound["message"] = message.replace(temp_stem, target_stem) if relocate else message

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

        phase["value"] = "preparing"
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
                relocate = not download_only
                temp_filepath = os.path.join(WORKSPACE_DIR, script_name)
                with open(temp_filepath, "w", encoding="utf-8") as f:
                    f.write(code_content)

            phase["value"] = "rendering"
            result = await conn_executor.execute(
                manim_path=manim_command,
                script_name=script_name,
                scene_name=request["scene"],
                quality=request["quality"],
                use_opengl=request["use_opengl"],
                log_callback=log_callback,
            )
            phase["value"] = "finishing"
            if relocate and held_output and result.get("success"):
                moved = await asyncio.to_thread(_relocate_temp_output, held_output[-1], temp_stem, target_stem)
                final_path = moved or held_output[-1]
                await send({**_file_ready_event(final_path, media_rel_path(final_path)), "render_id": render_id})
        except asyncio.CancelledError:
            await conn_executor.cancel()
            result = {"success": False, "status": "cancelled"}
            raise
        except Exception as e:
            result = {"success": False, "status": "error", "error": str(e)}
            await send({"type": "error", "render_id": render_id, "message": f"Render execution error: {e}"})
        finally:
            phase["value"] = None
            # Clean up before the last await, so a cancellation during the send can't skip it.
            if temp_filepath:
                try:
                    os.remove(temp_filepath)
                except OSError:
                    pass
            if relocate and temp_stem:
                _remove_temp_media(temp_stem)
            await send(
                {
                    "type": "result",
                    "render_id": render_id,
                    "success": bool(result.get("success")),
                    "status": result.get("status", "unknown"),
                    "details": result,
                }
            )

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await send({"type": "error", "message": "Invalid JSON message."})
                continue
            if not isinstance(message, dict):
                await send({"type": "error", "message": "Message payload must be a JSON object."})
                continue

            msg_type = message.get("type")
            if msg_type == "start":
                render_id = message.get("id")
                if current_render_task and not current_render_task.done():
                    await stop_current_render()
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

                current_render_task = asyncio.create_task(run_render(request, render_id, manim_command))

            elif msg_type == "cancel":
                if current_render_task and not current_render_task.done():
                    if phase["value"] == "preparing":
                        current_render_task.cancel()
                    elif phase["value"] == "rendering":
                        # Stops Manim (or stops it as soon as it has been spawned); the
                        # render task then reports the "cancelled" result.
                        await conn_executor.cancel()
                    else:
                        # Manim already finished; let the output and result through.
                        continue
                    await send({"type": "info", "message": "Stopping render..."})

    except WebSocketDisconnect:
        await stop_current_render()
    except Exception as e:
        await stop_current_render()
        await send({"type": "error", "message": f"Server WebSocket error: {e}"})


# Serve the built frontend (index.html + static files). /assets is handled above.
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:

    @app.get("/")
    def read_root():
        return read_status()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
