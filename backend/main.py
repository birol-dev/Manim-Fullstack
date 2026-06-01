import os
import ast
import json
import shutil
import asyncio
from typing import List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from diagnostics import generate_profile, write_manim_config_file
from executor import ManimExecutor

app = FastAPI(title="Manim Video Editor Backend")

# Configure CORS so our React frontend on localhost:5173 can connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For local development, allow all
    allow_credentials=True,
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
    
    scenes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Check if it inherits from something (most scenes inherit from Scene, ThreeDScene etc.)
            if node.bases:
                scenes.append(node.name)
            # Or if it's explicitly named scene
            elif "scene" in node.name.lower():
                scenes.append(node.name)
    return scenes

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
                if isinstance(subnode, ast.FunctionDef) and subnode.name == "construct":
                    construct_node = subnode
                    break
            
            if not construct_node:
                continue
                
            anims = []
            for stmt in construct_node.body:
                # We inspect Expr statements that hold Call values
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                    call = stmt.value
                    if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name) and call.func.value.id == "self":
                        if call.func.attr == "play":
                            line_no = stmt.lineno
                            try:
                                # ast.unparse is available in Python 3.9+
                                args_str = ", ".join(ast.unparse(arg) for arg in call.args)
                                anims.append({
                                    "type": "play",
                                    "label": f"Play: {args_str}",
                                    "line": line_no
                                })
                            except Exception:
                                anims.append({
                                    "type": "play",
                                    "label": "Play animation",
                                    "line": line_no
                                })
                        elif call.func.attr == "wait":
                            line_no = stmt.lineno
                            duration = 1.0
                            if call.args:
                                try:
                                    duration_str = ast.unparse(call.args[0])
                                    if duration_str.replace('.', '', 1).isdigit():
                                        duration = float(duration_str)
                                    else:
                                        duration = duration_str
                                except Exception:
                                    pass
                            anims.append({
                                "type": "wait",
                                "label": f"Wait {duration}s",
                                "duration": duration,
                                "line": line_no
                            })
            if anims:
                scene_anims[scene_name] = anims
    return scene_anims

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
        if file.endswith(".py"):
            full_path = os.path.join(WORKSPACE_DIR, file)
            scripts.append({
                "name": file,
                "size": os.path.getsize(full_path),
                "type": "script"
            })

    # 2. Scan for asset uploads (SVGs, PNGs, MP3s, etc.)
    if os.path.exists(ASSETS_DIR):
        for file in os.listdir(ASSETS_DIR):
            full_path = os.path.join(ASSETS_DIR, file)
            assets.append({
                "name": file,
                "size": os.path.getsize(full_path),
                "type": "asset",
                "url": f"/assets/{file}"
            })

    # 3. Recursively find rendered videos (MP4, GIF, WebM) in media/videos/
    videos_dir = os.path.join(MEDIA_DIR, "videos")
    if os.path.exists(videos_dir):
        for root, dirs, files in os.walk(videos_dir):
            if "partial_movie_files" in root.replace("\\", "/").split("/"):
                continue
            for file in files:
                if file.endswith((".mp4", ".gif", ".mov", ".webm")):
                    full_path = os.path.join(root, file)
                    # Get path relative to MEDIA_DIR to form the static URL
                    rel_path = os.path.relpath(full_path, MEDIA_DIR).replace("\\", "/")
                    media_files.append({
                        "name": file,
                        "size": os.path.getsize(full_path),
                        "type": "video",
                        "url": f"/media/{rel_path}"
                    })

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
        with open(os.path.join(WORKSPACE_DIR, default_script_name), "w") as f:
            f.write(default_script_content)
        scripts.append({
            "name": default_script_name,
            "size": len(default_script_content),
            "type": "script"
        })

    return {
        "scripts": scripts,
        "assets": assets,
        "media": media_files
    }

@app.get("/api/file-content")
def get_file_content(filename: str):
    """Returns the code content of a specific script."""
    filepath = os.path.join(WORKSPACE_DIR, filename)
    if not os.path.exists(filepath) or not filename.endswith(".py"):
        raise HTTPException(status_code=404, detail="Python script not found.")
    
    with open(filepath, "r") as f:
        content = f.read()
    
    return {
        "filename": filename,
        "code": content,
        "scenes": get_scenes_from_code(content),
        "animations": get_scene_animations(content)
    }

@app.post("/api/save")
def save_file(req: SaveRequest):
    """Saves code to a python script, returning parsed scenes."""
    filename = req.filename
    if not filename.endswith(".py"):
        filename += ".py"
        
    filepath = os.path.join(WORKSPACE_DIR, filename)
    
    try:
        with open(filepath, "w") as f:
            f.write(req.code)
        
        scenes = get_scenes_from_code(req.code)
        animations = get_scene_animations(req.code)
        return {
            "success": True,
            "filename": filename,
            "scenes": scenes,
            "animations": animations,
            "message": "File saved successfully."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class RenameRequest(BaseModel):
    old_name: str
    new_name: str

@app.post("/api/rename")
def rename_file(req: RenameRequest):
    """Renames a python script in the workspace."""
    old_name = req.old_name
    new_name = req.new_name
    
    if not old_name.endswith(".py") or not new_name.endswith(".py"):
        raise HTTPException(status_code=400, detail="Only python (.py) scripts can be renamed.")
        
    old_path = os.path.join(WORKSPACE_DIR, old_name)
    new_path = os.path.join(WORKSPACE_DIR, new_name)
    
    if not os.path.exists(old_path):
        raise HTTPException(status_code=404, detail="Source file not found.")
        
    if os.path.exists(new_path):
        raise HTTPException(status_code=400, detail="A file with the target name already exists.")
        
    try:
        os.rename(old_path, new_path)
        return {
            "success": True, 
            "old_name": old_name, 
            "new_name": new_name, 
            "message": f"Renamed {old_name} to {new_name}."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload-asset")
async def upload_asset(file: UploadFile = File(...)):
    """Handles asset uploads (audio, SVGs, images) to workspace/assets/."""
    filename = file.filename
    dest_path = os.path.join(ASSETS_DIR, filename)
    
    try:
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        return {
            "success": True,
            "filename": filename,
            "url": f"/assets/{filename}"
        }
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
            custom_winget = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\winget.exe")
            if os.path.exists(custom_winget):
                winget_path = custom_winget
            else:
                raise HTTPException(status_code=400, detail="winget package manager is not installed on this system.")
                
        # Launch winget in a subprocess in the background
        import platform
        import subprocess
        cmd = [
            winget_path, "install", "--id", "MikTeX.MikTeX", 
            "--silent", "--accept-source-agreements", "--accept-package-agreements"
        ]
        
        subprocess.Popen(
            cmd, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
        )
        
        return {
            "success": True,
            "message": "MiKTeX installer has been started in the background. Please accept any UAC prompt that appears."
        }
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
            message = json.loads(data)
            
            msg_type = message.get("type")
            
            if msg_type == "start":
                # Start render command parameters
                filename = message.get("filename")
                scene_name = message.get("scene")
                quality = message.get("quality", "m")
                use_opengl = message.get("use_opengl", False)
                
                # Fetch absolute paths
                binaries = get_binary_paths()
                manim_path = binaries["manim"]
                
                if manim_path == "Not Found":
                    await websocket.send_json({
                        "type": "error",
                        "message": "Manim executable not found on the system. Please verify installation path."
                    })
                    continue
                
                # Define callback function to stream logs and progress to WebSocket
                def log_callback(log_event):
                    # We run this in an async-friendly way or execute it directly
                    asyncio.create_task(websocket.send_json(log_event))

                # Launch async rendering
                result = await executor.execute(
                    manim_path=manim_path,
                    script_name=filename,
                    scene_name=scene_name,
                    quality=quality,
                    use_opengl=use_opengl,
                    log_callback=log_callback
                )
                
                # Report final rendering result
                await websocket.send_json({
                    "type": "result",
                    "success": result["success"],
                    "status": result["status"],
                    "details": result
                })
                
            elif msg_type == "cancel":
                # Cancel the active render task
                await executor.cancel()
                await websocket.send_json({
                    "type": "info",
                    "message": "Cancellation request received. Stopping render processes..."
                })
                
    except WebSocketDisconnect:
        # If client disconnects, clean up and terminate running processes
        await executor.cancel()
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": f"Server WebSocket error: {str(e)}"})
        except Exception:
            pass

def get_binary_paths():
    """Local helper mirroring diagnostic utility path finding."""
    manim_path = shutil.which("manim")
    if not manim_path:
        custom_manim = r"C:\tools\Manim\Scripts\manim.exe"
        if os.path.exists(custom_manim):
            manim_path = custom_manim
    return {"manim": manim_path or "Not Found"}

if __name__ == "__main__":
    import uvicorn
    # Start server on local port 8000
    uvicorn.run(app, host="127.0.0.1", port=8000)
