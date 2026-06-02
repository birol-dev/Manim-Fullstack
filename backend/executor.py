import asyncio
import os
import re
import subprocess
import sys
import platform

class ManimExecutor:
    def __init__(self, workspace_dir: str):
        self.workspace_dir = workspace_dir
        self.current_process = None
        self._cancelled = False

    async def execute(self, manim_path: str, script_name: str, scene_name: str, quality: str, use_opengl: bool, log_callback):
        """
        Executes the manim command in a subprocess, parsing output and streaming logs/progress.
        
        quality options: 'l' (low), 'm' (medium), 'h' (high), 'k' (4k)
        """
        self._cancelled = False
        self.current_process = None

        # Build command list
        # Ensure we run using the absolute paths and right flags
        cmd = [manim_path, script_name, scene_name]
        
        # Quality flags
        if quality in ["l", "m", "h", "k"]:
            cmd.append(f"-q{quality}")
        else:
            cmd.append("-qm") # default medium

        # OpenGL renderer flag
        if use_opengl:
            cmd.append("--renderer=opengl")
            # In OpenGL mode, prevent opening interactive window and force writing to file
            cmd.append("--write_to_movie")
        
        # We always want it to output progress bar to stdout
        cmd.append("--progress_bar=display")

        log_callback({"type": "info", "message": f"Starting command: {' '.join(cmd)}"})

        try:
            # Run the command asynchronously
            # We set stdout and stderr to PIPE so we can read them
            self.current_process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workspace_dir,
                # On Windows, hide the console window for child processes if running in GUI context
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )

            # We create two tasks to read stdout and stderr concurrently
            stdout_task = asyncio.create_task(self._read_stream(self.current_process.stdout, "stdout", log_callback))
            stderr_task = asyncio.create_task(self._read_stream(self.current_process.stderr, "stderr", log_callback))

            await asyncio.gather(stdout_task, stderr_task)
            
            # Wait for exit code
            exit_code = await self.current_process.wait()
            self.current_process = None

            if self._cancelled:
                log_callback({"type": "status", "status": "cancelled", "message": "Rendering was cancelled by user."})
                return {"success": False, "status": "cancelled"}

            if exit_code == 0:
                log_callback({"type": "status", "status": "success", "message": "Rendering completed successfully."})
                return {"success": True, "status": "success"}
            else:
                log_callback({"type": "status", "status": "failed", "message": f"Rendering failed with exit code {exit_code}."})
                return {"success": False, "status": "failed", "exit_code": exit_code}

        except Exception as e:
            log_callback({"type": "error", "message": f"Executor error: {str(e)}"})
            return {"success": False, "status": "error", "error": str(e)}

    async def cancel(self):
        """Cancels the active rendering process, killing it and all child processes recursively."""
        if self.current_process:
            self._cancelled = True
            pid = self.current_process.pid
            try:
                if platform.system() == "Windows":
                    # On Windows, kill the process tree (/T) forcefully (/F)
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], 
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    self.current_process.terminate()
            except Exception:
                pass

    async def _read_stream(self, stream, stream_name, log_callback):
        """Asynchronously reads a stream line-by-line and extracts progress/errors."""
        # Regular expressions to parse progress and output files
        # Manim CE typical progress: "[ 50%] 30/60"
        progress_pattern = re.compile(r"\[\s*(\d+)%\]")
        # Video file pattern: matches "File ready at 'path'", "File ready at: path", "File ready at path", and handles ANSI color codes
        file_pattern = re.compile(
            r"File ready at(?:\s+|:\s+)"
            r"(?:\x1b\[[0-9;]*m)?"
            r"['\"]?"
            r"([^\x1b'\"\r\n\t]+)"
            r"['\"]?"
            r"(?:\x1b\[[0-9;]*m)?"
        )
        # LaTeX errors: "LaTeX compilation error" or "xelatex is not installed"
        latex_pattern = re.compile(r"LaTeX|dvisvgm|svg|pdf", re.IGNORECASE)

        while True:
            line_bytes = await stream.readline()
            if not line_bytes:
                break
            
            # Decode line with fallback
            try:
                line = line_bytes.decode("utf-8")
            except UnicodeDecodeError:
                line = line_bytes.decode("latin-1", errors="replace")
            
            clean_line = line.rstrip()
            if not clean_line:
                continue

            # Stream raw line to console log
            log_callback({"type": "log", "stream": stream_name, "message": clean_line})

            # Check for progress
            progress_match = progress_pattern.search(clean_line)
            if progress_match:
                percent = int(progress_match.group(1))
                log_callback({"type": "progress", "percent": percent, "line": clean_line})

            # Check for file path (output video)
            file_match = file_pattern.search(clean_line)
            if file_match:
                video_path = file_match.group(1)
                if video_path:
                    # Strip potential leftover quote/whitespace chars from the path
                    video_path = video_path.strip().strip("'\"")
                    # Resolve relative to workspace if needed
                    abs_video_path = os.path.abspath(os.path.join(self.workspace_dir, video_path))
                    # Convert to web-friendly relative path or just return filename
                    filename = os.path.basename(abs_video_path)
                    
                    # Compute relative path from media folder or just expose it
                    # Manim writes to: media/videos/<script_name>/<quality>/<scene_name>.mp4
                    # We will serve 'media' folder, so we want the path relative to media directory
                    # Let's find index of 'media' in the path
                    media_rel_path = ""
                    normalized_path = abs_video_path.replace("\\", "/")
                    if "/media/" in normalized_path:
                        media_rel_path = "media" + normalized_path.split("/media")[-1]
                    else:
                        media_rel_path = filename

                    print(f"DEBUG: matched video path: {video_path} -> abs: {abs_video_path} -> rel: {media_rel_path}", flush=True)

                    log_callback({
                        "type": "file_ready", 
                        "abs_path": abs_video_path,
                        "rel_path": media_rel_path,
                        "filename": filename
                    })

            # Check for LaTeX specific errors to give user helpful hints
            if latex_pattern.search(clean_line) and ("error" in clean_line.lower() or "fail" in clean_line.lower() or "not found" in clean_line.lower()):
                log_callback({
                    "type": "latex_error_warning",
                    "message": "It looks like LaTeX rendering failed. If LaTeX is not installed or dvisvgm is missing, please replace MathTex elements with standard Text, or download MiKTeX/TeX Live."
                })
