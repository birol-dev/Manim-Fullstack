import ast
import json
import os
import shutil
import sys
from urllib.parse import quote

# Ensure backend directory is in python search path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from typing import List

from diagnostics import generate_profile, get_binary_paths, write_manim_config_file
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


def get_scenes_from_code(code_content: str) -> List[str]:
    """Parses Python code using AST to find all classes representing Scenes."""
    try:
        tree = ast.parse(code_content)
    except Exception:
        # If there's a syntax error, we just return empty list
        return []

    scene_nodes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Check if it inherits from something (most scenes inherit from Scene, ThreeDScene etc.)
            if node.bases or "scene" in node.name.lower():
                scene_nodes.append((getattr(node, "lineno", 0), node.name))
    scene_nodes.sort(key=lambda x: x[0])
    return [name for _, name in scene_nodes]


def get_scene_animations(code_content: str) -> dict:
    """Parses Python code using AST to find self.play and self.wait calls in each Scene's construct method."""
    try:
        tree = ast.parse(code_content)
    except Exception:
        return {}

    scene_anims = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            scene_name = node.name

            # Check if it has a construct method
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
                                # ast.unparse is available in Python 3.9+
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
                            duration_label = f"{duration}s" if isinstance(duration, (int, float)) or (isinstance(duration, str) and not duration.endswith("s")) else f"{duration}"
                            anims.append(
                                {
                                    "type": "wait",
                                    "label": f"Wait {duration_label}",
                                    "duration": duration,
                                    "line": line_no,
                                }
                            )
            if anims:
                # Sort animations by line number chronologically
                anims.sort(key=lambda x: x["line"])
                scene_anims[scene_name] = anims
    return scene_anims


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
    return generate_profile()


@app.get("/api/files")
def get_files():
    """Lists python scripts in workspace, uploaded assets, and rendered media."""
    scripts = []
    assets = []
    media_files = []

    # 1. Scan for Python scripts
    for file in os.listdir(WORKSPACE_DIR):
        if not file.endswith(".py") or file.startswith("_temp_run_"):
            continue
        full_path = os.path.join(WORKSPACE_DIR, file)
        if not os.path.isfile(full_path):
            continue
        scripts.append(
            {"name": file, "size": os.path.getsize(full_path), "type": "script"}
        )

    # 2. Scan for asset uploads (SVGs, PNGs, MP3s, etc.)
    if os.path.exists(ASSETS_DIR):
        for file in os.listdir(ASSETS_DIR):
            full_path = os.path.join(ASSETS_DIR, file)
            if not os.path.isfile(full_path):
                continue
            assets.append(
                {
                    "name": file,
                    "size": os.path.getsize(full_path),
                    "type": "asset",
                    "url": f"/assets/{quote(file)}",
                }
            )

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
                    # Get path relative to MEDIA_DIR to form the static URL
                    rel_path = os.path.relpath(full_path, MEDIA_DIR).replace("\\", "/")
                    encoded_rel = "/".join(quote(part) for part in rel_path.split("/"))
                    media_files.append(
                        {
                            "name": file,
                            "size": os.path.getsize(full_path),
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

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

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
    clean_path = path.strip().replace("\\", "/").lstrip("/")
    if clean_path.startswith("media/"):
        clean_path = clean_path[len("media/"):]

    try:
        abs_path = safe_join(MEDIA_DIR, clean_path)
    except UnsafePathError:
        raise HTTPException(status_code=400, detail="Access denied")

    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="File not found")

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
    return FileResponse(abs_path, media_type="video/mp4", filename=os.path.basename(abs_path))


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

    try:
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return {"success": True, "filename": filename, "url": f"/assets/{quote(filename)}"}
    except Exception as e:
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

            msg_type = message.get("type")

            if msg_type == "start":
                # Start render command parameters
                filename = message.get("filename")
                scene_name = message.get("scene")
                quality = message.get("quality", "m")
                use_opengl = message.get("use_opengl", False)
                download_only = message.get("download_only", False)
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

                # Fetch absolute paths
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

                # Define callback function to stream logs and progress to WebSocket
                async def log_callback(log_event):
                    try:
                        if download_only and log_event.get("type") == "file_ready":
                            # Rewrite the rel_path to point to the download-temp endpoint
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
                        pass

                # Handle transient code content via a temporary script file
                temp_filepath = None
                actual_script_name = filename

                if code_content is not None:
                    import uuid
                    temp_id = uuid.uuid4().hex[:8]
                    actual_script_name = f"_temp_run_{temp_id}.py"
                    temp_filepath = os.path.join(WORKSPACE_DIR, actual_script_name)
                    with open(temp_filepath, "w", encoding="utf-8") as f:
                        f.write(code_content)

                try:
                    # Launch async rendering
                    result = await executor.execute(
                        manim_path=manim_path,
                        script_name=actual_script_name,
                        scene_name=scene_name,
                        quality=quality,
                        use_opengl=use_opengl,
                        log_callback=log_callback,
                    )
                finally:
                    # Cleanup the temporary script file if created
                    if temp_filepath and os.path.exists(temp_filepath):
                        try:
                            os.remove(temp_filepath)
                        except Exception:
                            pass

                # Report final rendering result
                await websocket.send_json(
                    {
                        "type": "result",
                        "success": result["success"],
                        "status": result["status"],
                        "details": result,
                    }
                )

            elif msg_type == "cancel":
                # Cancel the active render task
                await executor.cancel()
                await websocket.send_json(
                    {
                        "type": "info",
                        "message": "Cancellation request received. Stopping render processes...",
                    }
                )

    except WebSocketDisconnect:
        # If client disconnects, clean up and terminate running processes
        await executor.cancel()
    except Exception as e:
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

