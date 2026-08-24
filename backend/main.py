import ast
import asyncio
import json
import os
import shutil
import sys
from urllib.parse import quote

# Ensure backend directory is in python search path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from functools import lru_cache
from typing import List, Optional

from diagnostics import (
    generate_profile,
    get_binary_paths,
    get_cached_profile,
    get_cached_binary_paths,
    write_manim_config_file,
)
from executor import ManimExecutor
from workspace_paths import UnsafePathError, safe_basename, safe_join
from fastapi import (
    FastAPI,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    BackgroundTasks,
)
from fastapi.responses import FileResponse

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="Manim Video Editor Backend")

# Configure CORS so our React frontend on localhost:5173 can connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For local development, allow all
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup workspace directories in the main project folder
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_DIR = os.path.join(BASE_DIR, "workspace")
MEDIA_DIR = os.path.join(WORKSPACE_DIR, "media")
ASSETS_DIR = os.path.join(WORKSPACE_DIR, "assets")

for path in [WORKSPACE_DIR, MEDIA_DIR, ASSETS_DIR]:
    os.makedirs(path, exist_ok=True)

# Generate config profile and write manim.cfg to workspace
sys_profile = generate_profile()
write_manim_config_file(WORKSPACE_DIR, sys_profile)

# Mount static files to serve media (rendered videos) and assets (uploaded SVGs/audio)
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

# Active executor instance
executor = ManimExecutor(WORKSPACE_DIR)


class SaveRequest(BaseModel):
    filename: str
    code: str


class FileInfo(BaseModel):
    name: str
    path: str
    size: int
    is_media: bool


@lru_cache(maxsize=512)
def _parse_code_ast(code_content: str) -> tuple:
    """
    Parses Python code using AST in a single pass to extract scenes and animation timeline.
    Cached via LRU cache for instantaneous subsequent lookups.
    """
    try:
        tree = ast.parse(code_content)
    except Exception:
        return ((), ())

    scene_nodes = []
    scene_anims = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if node.bases or "scene" in node.name.lower():
                scene_nodes.append((getattr(node, "lineno", 0), node.name))

            construct_node = None
            for subnode in node.body:
                if isinstance(subnode, (ast.FunctionDef, ast.AsyncFunctionDef)) and subnode.name == "construct":
                    construct_node = subnode
                    break

            if not construct_node:
                continue

            anims = []
            for subnode in ast.walk(construct_node):
                if isinstance(subnode, ast.Call):
                    if (
                        isinstance(subnode.func, ast.Attribute)
                        and isinstance(subnode.func.value, ast.Name)
                        and subnode.func.value.id == "self"
                    ):
                        if subnode.func.attr == "play":
                            line_no = subnode.lineno
                            try:
                                args_str = ", ".join(
                                    ast.unparse(arg) for arg in subnode.args
                                )
                                anims.append(
                                    {
                                        "type": "play",
                                        "label": f"Play: {args_str}",
                                        "line": line_no,
                                    }
                                )
                            except Exception:
                                anims.append(
                                    {
                                        "type": "play",
                                        "label": "Play animation",
                                        "line": line_no,
                                    }
                                )
                        elif subnode.func.attr == "wait":
                            line_no = subnode.lineno
                            duration = 1.0
                            if subnode.args:
                                try:
                                    duration_str = ast.unparse(subnode.args[0])
                                    if duration_str.replace(".", "", 1).isdigit():
                                        duration = float(duration_str)
                                    else:
                                        duration = duration_str
                                except Exception:
                                    pass
                            elif subnode.keywords:
                                for kw in subnode.keywords:
                                    if kw.arg in ("duration", "run_time"):
                                        try:
                                            duration_str = ast.unparse(kw.value)
                                            if duration_str.replace(".", "", 1).isdigit():
                                                duration = float(duration_str)
                                            else:
                                                duration = duration_str
                                        except Exception:
                                            pass
                            duration_label = (
                                f"{duration}s"
                                if isinstance(duration, (int, float))
                                or (isinstance(duration, str) and not duration.endswith("s"))
                                else f"{duration}"
                            )
                            anims.append(
                                {
                                    "type": "wait",
                                    "label": f"Wait {duration_label}",
                                    "duration": duration,
                                    "line": line_no,
                                }
                            )
            if anims:
                anims.sort(key=lambda x: x["line"])
                scene_anims[node.name] = tuple(tuple(d.items()) for d in anims)

    scene_nodes.sort(key=lambda x: x[0])
    return (tuple(name for _, name in scene_nodes), tuple(scene_anims.items()))


def get_scenes_from_code(code_content: str) -> List[str]:
    """Parses Python code using AST to find all classes representing Scenes."""
    scenes_tuple, _ = _parse_code_ast(code_content)
    return list(scenes_tuple)


def get_scene_animations(code_content: str) -> dict:
    """Parses Python code using AST to find self.play and self.wait calls in each Scene's construct method."""
    _, anims_tuple = _parse_code_ast(code_content)
    res = {}
    for scene_name, anim_items in anims_tuple:
        res[scene_name] = [dict(item) for item in anim_items]
    return res


@app.get("/api/status")
@app.get("/api/health")
def read_status():
    return {
        "status": "online",
        "service": "Manim Composer API",
        "version": "0.18.1 CE",
        "docs": "/docs",
    }


@app.get("/api/diagnostics")
def get_diagnostics():
    """Returns hardware diagnostics and rendering configuration profile."""
    return get_cached_profile()


@app.get("/api/files")
def get_files():
    """Lists python scripts in workspace, uploaded assets, and rendered media."""
    scripts = []
    assets = []
    media_files = []

    # 1. Scan for Python scripts using fast scandir
    try:
        with os.scandir(WORKSPACE_DIR) as entries:
            for entry in entries:
                if entry.is_file() and entry.name.endswith(".py") and not entry.name.startswith("_temp_run_"):
                    try:
                        scripts.append(
                            {"name": entry.name, "size": entry.stat().st_size, "type": "script"}
                        )
                    except OSError:
                        pass
    except OSError:
        pass

    # 2. Scan for asset uploads (SVGs, PNGs, MP3s, etc.)
    if os.path.exists(ASSETS_DIR):
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

    # 3. Recursively find rendered videos (MP4, GIF, WebM) in media/videos/
    videos_dir = os.path.join(MEDIA_DIR, "videos")
    if os.path.exists(videos_dir):
        for root, dirs, files in os.walk(videos_dir):
            root_parts = root.replace("\\", "/").split("/")
            if "partial_movie_files" in root_parts or any(p.startswith("_temp_run_") for p in root_parts):
                continue
            for file in files:
                if file.endswith((".mp4", ".gif", ".mov", ".webm")):
                    full_path = os.path.join(root, file)
                    try:
                        file_size = os.path.getsize(full_path)
                    except OSError:
                        file_size = 0
                    rel_path = os.path.relpath(full_path, MEDIA_DIR).replace("\\", "/")
                    encoded_rel = "/".join(quote(part) for part in rel_path.split("/"))
                    media_files.append(
                        {
                            "name": file,
                            "size": file_size,
                            "type": "video",
                            "url": f"/media/{encoded_rel}",
                        }
                    )

    scripts.sort(key=lambda s: s["name"].lower())
    assets.sort(key=lambda a: a["name"].lower())
    media_files.sort(key=lambda m: m["name"].lower())


    # If workspace is empty, write a default example script so the user starts with something
    if not scripts:
        default_script_name = "example.py"
        default_script_content = """from manim import *

class SquareToCircle(Scene):
    def construct(self):
        # Create shapes
        circle = Circle(color=PINK)
        square = Square(color=BLUE)
        square.flip(RIGHT)
        square.rotate(PI / 8)

        # Show shapes
        self.play(Create(square))
        self.play(Transform(square, circle))
        self.play(FadeOut(square))

class WriteFormula(Scene):
    def construct(self):
        # Create standard Text elements.
        # (Using Text instead of MathTex because LaTeX isn't installed locally)
        title = Text("Manim Video Editor", font_size=40, color=YELLOW)
        subtitle = Text("Render math and animations cleanly", font_size=28, color=WHITE)

        # Position them
        title.shift(UP * 0.8)
        subtitle.next_to(title, DOWN)

        # Draw them
        self.play(Write(title))
        self.play(FadeIn(subtitle, shift=UP))
        self.wait(1.5)
        self.play(FadeOut(title), FadeOut(subtitle))
"""
        with open(
            os.path.join(WORKSPACE_DIR, default_script_name), "w", encoding="utf-8"
        ) as f:
            f.write(default_script_content)
        scripts.append(
            {
                "name": default_script_name,
                "size": len(default_script_content),
                "type": "script",
            }
        )

    return {"scripts": scripts, "assets": assets, "media": media_files}


@app.get("/api/file-content")
def get_file_content(filename: str):
    """Returns the code content of a specific script."""
    try:
        filename = safe_basename(filename, required_suffix=".py")
        filepath = safe_join(WORKSPACE_DIR, filename)
    except UnsafePathError:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="Python script not found.")

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")

    return {
        "filename": filename,
        "code": content,
        "scenes": get_scenes_from_code(content),
        "animations": get_scene_animations(content),
    }


class ParseRequest(BaseModel):
    code: str


@app.post("/api/parse-code")
def parse_code(req: ParseRequest):
    """Parses code on the fly to return scenes and animations without writing to disk."""
    scenes = get_scenes_from_code(req.code)
    animations = get_scene_animations(req.code)
    return {
        "success": True,
        "scenes": scenes,
        "animations": animations,
    }


@app.get("/api/download-temp")
def download_temp(path: str, background_tasks: BackgroundTasks):
    """Serves a rendered temporary file and deletes it once the download completes."""
    import mimetypes

    clean_path = path.strip().replace("\\", "/").lstrip("/")
    if clean_path.startswith("media/"):
        clean_path = clean_path[len("media/"):]

    try:
        abs_path = safe_join(MEDIA_DIR, clean_path)
    except UnsafePathError:
        raise HTTPException(status_code=400, detail="Access denied")

    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="File not found")

    guessed_type, _ = mimetypes.guess_type(abs_path)
    media_type = guessed_type or "video/mp4"

    def remove_file():
        try:
            if os.path.exists(abs_path):
                os.remove(abs_path)
            # If parent or grandparent is a temporary render directory, remove the whole tree
            parent = os.path.dirname(abs_path)
            grandparent = os.path.dirname(parent)
            if os.path.basename(grandparent).startswith("_temp_run_") and os.path.isdir(grandparent):
                shutil.rmtree(grandparent, ignore_errors=True)
            elif os.path.basename(parent).startswith("_temp_run_") and os.path.isdir(parent):
                shutil.rmtree(parent, ignore_errors=True)
            else:
                if os.path.exists(parent) and not os.listdir(parent):
                    os.rmdir(parent)
        except Exception:
            pass

    background_tasks.add_task(remove_file)
    return FileResponse(abs_path, media_type=media_type, filename=os.path.basename(abs_path))


@app.post("/api/save")
def save_file(req: SaveRequest):
    """Saves code to a python script, returning parsed scenes."""
    filename = req.filename
    if not filename.endswith(".py"):
        filename += ".py"

    try:
        filename = safe_basename(filename, required_suffix=".py")
        filepath = safe_join(WORKSPACE_DIR, filename)
    except UnsafePathError:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(req.code)

        scenes = get_scenes_from_code(req.code)
        animations = get_scene_animations(req.code)
        return {
            "success": True,
            "filename": filename,
            "scenes": scenes,
            "animations": animations,
            "message": "File saved successfully.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RenameRequest(BaseModel):
    old_name: str
    new_name: str


@app.post("/api/rename")
def rename_file(req: RenameRequest):
    """Renames a python script in the workspace."""
    try:
        old_name = safe_basename(req.old_name, required_suffix=".py")
        new_name = safe_basename(req.new_name, required_suffix=".py")
        old_path = safe_join(WORKSPACE_DIR, old_name)
        new_path = safe_join(WORKSPACE_DIR, new_name)
    except UnsafePathError:
        raise HTTPException(
            status_code=400,
            detail="Only python (.py) scripts in the workspace can be renamed.",
        )

    if not os.path.exists(old_path):
        raise HTTPException(status_code=404, detail="Source file not found.")

    is_case_only = os.path.normcase(old_path) == os.path.normcase(new_path)
    if os.path.exists(new_path) and not is_case_only:
        raise HTTPException(
            status_code=400, detail="A file with the target name already exists."
        )

    try:
        if is_case_only and old_name != new_name:
            import uuid
            temp_name = f"__tmp_rename_{uuid.uuid4().hex[:8]}_{old_name}"
            temp_path = safe_join(WORKSPACE_DIR, temp_name)
            os.rename(old_path, temp_path)
            os.rename(temp_path, new_path)
        else:
            os.rename(old_path, new_path)

        return {
            "success": True,
            "old_name": old_name,
            "new_name": new_name,
            "message": f"Renamed {old_name} to {new_name}.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



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


@app.post("/api/upload-asset")
async def upload_asset(file: UploadFile = File(...)):
    """Handles asset uploads (audio, SVGs, images) to workspace/assets/."""
    try:
        filename = safe_basename(file.filename)
        dest_path = safe_join(ASSETS_DIR, filename)
    except UnsafePathError:
        raise HTTPException(
            status_code=400, detail="Uploaded file must include a valid filename."
        )

    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_ASSET_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported asset type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_ASSET_EXTENSIONS))}",
        )

    try:
        size = 0
        with open(dest_path, "wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_ASSET_SIZE_BYTES:
                    buffer.close()
                    if os.path.exists(dest_path):
                        try:
                            os.remove(dest_path)
                        except Exception:
                            pass
                    raise HTTPException(
                        status_code=413,
                        detail="File size exceeds maximum allowed size (50MB).",
                    )
                buffer.write(chunk)

        return {"success": True, "filename": filename, "url": f"/assets/{quote(filename)}"}
    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/install-latex")
def install_latex():
    """Triggers the silent installation of MiKTeX via winget in a separate process."""
    try:
        # Check if winget is available
        winget_path = shutil.which("winget")
        if not winget_path:
            # Try appdata local path
            custom_winget = os.path.expandvars(
                r"%LOCALAPPDATA%\Microsoft\WindowsApps\winget.exe"
            )
            if os.path.exists(custom_winget):
                winget_path = custom_winget
            else:
                raise HTTPException(
                    status_code=400,
                    detail="winget package manager is not installed on this system.",
                )

        # Launch winget in a subprocess in the background
        import platform
        import subprocess

        cmd = [
            winget_path,
            "install",
            "--id",
            "MiKTeX.MiKTeX",
            "--silent",
            "--accept-source-agreements",
            "--accept-package-agreements",
            "--scope",
            "user",
        ]

        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW
            if platform.system() == "Windows"
            else 0,
        )

        return {
            "success": True,
            "message": "MiKTeX installer has been started in the background. It will install silently in your user profile (no UAC prompt required).",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/install-ffmpeg")
def install_ffmpeg():
    """Triggers the silent installation of FFmpeg via winget in a separate process."""
    try:
        # Check if winget is available
        winget_path = shutil.which("winget")
        if not winget_path:
            # Try appdata local path
            custom_winget = os.path.expandvars(
                r"%LOCALAPPDATA%\Microsoft\WindowsApps\winget.exe"
            )
            if os.path.exists(custom_winget):
                winget_path = custom_winget
            else:
                raise HTTPException(
                    status_code=400,
                    detail="winget package manager is not installed on this system.",
                )

        # Launch winget in a subprocess in the background
        import platform
        import subprocess

        cmd = [
            winget_path,
            "install",
            "--id",
            "Gyan.FFmpeg",
            "--silent",
            "--accept-source-agreements",
            "--accept-package-agreements",
            "--scope",
            "user",
        ]

        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW
            if platform.system() == "Windows"
            else 0,
        )

        return {
            "success": True,
            "message": "FFmpeg installer has been started in the background. It will install silently in your user profile (no UAC prompt required).",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/install-manim")
def install_manim():
    """Triggers the pip installation of manim CE in the current python environment in a separate process."""
    try:
        import subprocess
        import sys

        # Check system python executable
        python_exe = sys.executable
        if not python_exe:
            raise HTTPException(
                status_code=400, detail="Python executable could not be identified."
            )

        cmd = [python_exe, "-m", "pip", "install", "manim"]

        # Launch process in background
        import platform

        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW
            if platform.system() == "Windows"
            else 0,
        )

        return {
            "success": True,
            "message": "Manim CE installation started in the background via pip.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/api/render")
async def websocket_render(websocket: WebSocket):
    """Handles real-time rendering processes over WebSockets."""
    await websocket.accept()
    current_render_task: Optional[asyncio.Task] = None

    async def run_render(
        manim_path: str,
        actual_script_name: str,
        scene_name: str,
        quality: str,
        use_opengl: bool,
        download_only: bool,
        temp_filepath: Optional[str],
    ):
        async def log_callback(log_event):
            try:
                if download_only and log_event.get("type") == "file_ready":
                    orig_rel_path = log_event.get("rel_path", "")
                    if orig_rel_path.startswith("media/"):
                        path_param = orig_rel_path[len("media/"):]
                    else:
                        path_param = orig_rel_path

                    log_event = dict(log_event)
                    log_event["rel_path"] = (
                        f"api/download-temp?path={quote(path_param)}"
                    )
                    log_event["is_temp_download"] = True

                await websocket.send_json(log_event)
            except (WebSocketDisconnect, RuntimeError):
                # Socket dropped or closed: signal cancel immediately
                await executor.cancel()

        try:
            result = await executor.execute(
                manim_path=manim_path,
                script_name=actual_script_name,
                scene_name=scene_name,
                quality=quality,
                use_opengl=use_opengl,
                log_callback=log_callback,
            )
            await websocket.send_json(
                {
                    "type": "result",
                    "success": result.get("success", False),
                    "status": result.get("status", "unknown"),
                    "details": result,
                }
            )
        except asyncio.CancelledError:
            await executor.cancel()
        except Exception as e:
            try:
                await websocket.send_json(
                    {"type": "error", "message": f"Render execution error: {str(e)}"}
                )
            except Exception:
                pass
        finally:
            if temp_filepath and os.path.exists(temp_filepath):
                try:
                    os.remove(temp_filepath)
                except Exception:
                    pass

    try:
        while True:
            # Expect a JSON text frame from the client
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {"type": "error", "message": "Invalid JSON message."}
                )
                continue

            if not isinstance(message, dict):
                await websocket.send_json(
                    {"type": "error", "message": "Message payload must be a JSON object."}
                )
                continue

            msg_type = message.get("type")

            if msg_type == "start":
                # If a previous render is still running on this connection, cancel it first
                if current_render_task and not current_render_task.done():
                    await executor.cancel()
                    current_render_task.cancel()
                    try:
                        await current_render_task
                    except (asyncio.CancelledError, Exception):
                        pass

                filename = message.get("filename")
                scene_name = message.get("scene")
                quality = message.get("quality", "m")
                use_opengl = bool(message.get("use_opengl", False))
                download_only = bool(message.get("download_only", False))
                code_content = message.get("code")

                if not filename or not scene_name:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "Render requests require both a filename and a scene name.",
                        }
                    )
                    continue

                if not isinstance(scene_name, str) or not scene_name.isidentifier():
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "Scene name must be a valid Python identifier.",
                        }
                    )
                    continue

                try:
                    safe_basename(filename, required_suffix=".py")
                except UnsafePathError:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "Invalid script filename.",
                        }
                    )
                    continue

                binaries = get_binary_paths()
                manim_path = binaries["manim"]

                if manim_path == "Not Found":
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "Manim executable not found on the system. Please verify installation path.",
                        }
                    )
                    continue

                temp_filepath = None
                actual_script_name = filename

                if code_content is not None:
                    import uuid
                    temp_id = uuid.uuid4().hex[:8]
                    actual_script_name = f"_temp_run_{temp_id}.py"
                    temp_filepath = os.path.join(WORKSPACE_DIR, actual_script_name)
                    with open(temp_filepath, "w", encoding="utf-8") as f:
                        f.write(code_content)

                current_render_task = asyncio.create_task(
                    run_render(
                        manim_path=manim_path,
                        actual_script_name=actual_script_name,
                        scene_name=scene_name,
                        quality=quality,
                        use_opengl=use_opengl,
                        download_only=download_only,
                        temp_filepath=temp_filepath,
                    )
                )

            elif msg_type == "cancel":
                await executor.cancel()
                if current_render_task and not current_render_task.done():
                    current_render_task.cancel()
                await websocket.send_json(
                    {
                        "type": "info",
                        "message": "Cancellation request received. Stopping render processes...",
                    }
                )

    except WebSocketDisconnect:
        await executor.cancel()
        if current_render_task and not current_render_task.done():
            current_render_task.cancel()
    except Exception as e:
        await executor.cancel()
        if current_render_task and not current_render_task.done():
            current_render_task.cancel()
        try:
            await websocket.send_json(
                {"type": "error", "message": f"Server WebSocket error: {str(e)}"}
            )
        except Exception:
            pass


# Serve frontend static assets if they exist (built React SPA)
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend", "dist")
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    @app.get("/")
    def read_root():
        return read_status()

if __name__ == "__main__":
    import uvicorn

    # Start server on local port 8000
    uvicorn.run(app, host="127.0.0.1", port=8000)

