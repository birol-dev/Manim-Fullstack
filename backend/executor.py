"""Runs Manim as a subprocess and streams its output as structured events.

Events passed to ``log_callback`` are plain dicts with a ``type`` key:

* ``info`` / ``error`` / ``status`` — lifecycle messages
* ``log`` — one line of Manim output (``stream`` is ``stdout`` or ``stderr``)
* ``progress`` — per-animation progress parsed from Manim's tqdm bars
* ``file_ready`` — the rendered video or image
* ``latex_error_warning`` — a hint that LaTeX is missing or failed (once per render)
"""

import asyncio
import codecs
import os
import platform
import re
import signal
import subprocess
import sys
import sysconfig
import tempfile

VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm")
IMAGE_EXTENSIONS = (".png", ".gif")
OUTPUT_EXTENSIONS = VIDEO_EXTENSIONS + IMAGE_EXTENSIONS

# CSI color/cursor codes, plus OSC and other short escapes Rich sometimes emits.
ANSI_PATTERN = re.compile(
    r"\x1b\[[0-9;?]*[A-Za-z]"
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    r"|\x1b[@-_]"
)
LINE_SPLIT_PATTERN = re.compile(r"\r\n|\r|\n")
# tqdm bar, e.g. "Animation 3: Create(Circle):  45%|████▌     | 27/60 [00:00<00:00]"
TQDM_PATTERN = re.compile(r"^(?:(?P<label>.*?):\s*)?(?P<percent>\d{1,3})%\|")
ANIMATION_LABEL_PATTERN = re.compile(r"^Animation\s+(?P<index>\d+)\s*:\s*(?P<name>.*)$")
# Older/bare progress format, e.g. "[ 50%] 30/60"
BRACKET_PROGRESS_PATTERN = re.compile(r"\[\s*(\d{1,3})%\]")
FILE_READY_PATTERN = re.compile(
    r"File ready at:?\s+(?:'(?P<single>[^']+)'|\"(?P<double>[^\"]+)\"|(?P<bare>\S+))"
)
FILE_READY_LEAD = re.compile(r"File ready at:?$")
# Rich log rows end with a right-aligned "module.py:123" column; it is noise in the UI.
RICH_SOURCE_COLUMN = re.compile(r"\s{2,}[\w.-]+\.py:\d+$")
RICH_LEVEL_ONLY = re.compile(r"^(?:\[[^\]]*\]\s+)?(?:DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
LATEX_PATTERN = re.compile(r"latex|dvisvgm", re.IGNORECASE)
FAILURE_PATTERN = re.compile(r"error|fail|not found|no such file", re.IGNORECASE)

LATEX_HINT = (
    "LaTeX rendering failed. MathTex and Tex need a LaTeX distribution (MiKTeX or TeX Live) "
    "with dvisvgm. Install one, or use Text(...) for plain labels."
)

# Rich wraps log lines to the terminal width (80 columns when piped), which splits
# long output paths across lines. A wide virtual terminal keeps them intact.
SUBPROCESS_COLUMNS = "400"
MAX_PENDING_LINE_CHARS = 64 * 1024
READ_CHUNK_BYTES = 8192

# Default render wall-clock timeout (seconds). Override with MANIM_RENDER_TIMEOUT.
DEFAULT_RENDER_TIMEOUT_SECONDS = float(os.environ.get("MANIM_RENDER_TIMEOUT", "600"))


def media_rel_path(abs_path: str) -> str:
    """Convert an absolute output path into a ``media/...`` path served by /media."""
    normalized = abs_path.replace("\\", "/")
    idx = normalized.rfind("/media/")
    if idx >= 0:
        return "media" + normalized[idx + len("/media"):]
    if normalized.startswith("media/"):
        return normalized
    return os.path.basename(abs_path)


def output_kind(path: str) -> str:
    """Return ``"image"`` or ``"video"`` for a rendered output path."""
    return "image" if path.lower().endswith(IMAGE_EXTENSIONS) else "video"


class ManimExecutor:
    def __init__(self, workspace_dir: str, render_timeout=None):
        self.workspace_dir = workspace_dir
        self.current_process = None
        self.render_timeout = (
            DEFAULT_RENDER_TIMEOUT_SECONDS if render_timeout is None else float(render_timeout)
        )
        self._cancelled = False
        self._executing = False
        self._cancel_pending = False
        self._last_file_ready = None
        self._pending_file_ready = None
        self._latex_warned = False
        self._last_progress = None
        self._previous_outputs = {}
        self._redaction = None

    @property
    def is_running(self) -> bool:
        return self.current_process is not None and self.current_process.returncode is None

    def _find_latest_render(self, script_name: str, scene_name: str, previous=None):
        """Locate the newest output for *script_name*/*scene_name* on disk.

        Used when the "File ready at" line could not be parsed from stdout.
        Videos are preferred; static scenes (no animations) produce an image instead.
        Files listed in *previous* (path -> stat signature, taken before Manim
        started) are skipped unless they changed, so a run that wrote nothing
        never reports an earlier run's video.
        """
        for path, signature in self._output_candidates(script_name, scene_name):
            if previous is not None and previous.get(path) == signature:
                continue
            return path
        return None

    def _output_snapshot(self, script_name: str, scene_name: str) -> dict:
        """Stat signatures of the outputs that already exist for this script and scene."""
        return dict(self._output_candidates(script_name, scene_name))

    def _output_candidates(self, script_name: str, scene_name: str):
        """(path, signature) pairs, newest first; videos before images."""
        script_stem = os.path.splitext(script_name)[0]
        media_dir = os.path.join(self.workspace_dir, "media")
        found = []
        for subdir, extensions in (("videos", VIDEO_EXTENSIONS), ("images", IMAGE_EXTENSIONS)):
            root_dir = os.path.join(media_dir, subdir, script_stem)
            found.extend(self._matching_files(root_dir, scene_name, extensions))
        return found

    @staticmethod
    def _matching_files(root_dir: str, scene_name: str, extensions):
        if not os.path.isdir(root_dir):
            return []
        candidates = []
        try:
            for root, _dirs, files in os.walk(root_dir):
                if "partial_movie_files" in root.replace("\\", "/").split("/"):
                    continue
                for name in files:
                    if not name.lower().endswith(extensions):
                        continue
                    stem = os.path.splitext(name)[0]
                    # Images are saved as "<Scene>_ManimCE_v<version>.png".
                    if scene_name and stem != scene_name and not stem.startswith(f"{scene_name}_ManimCE_"):
                        continue
                    full_path = os.path.join(root, name)
                    try:
                        info = os.stat(full_path)
                    except OSError:
                        continue
                    candidates.append((info.st_mtime_ns, full_path, (info.st_mtime_ns, info.st_size, info.st_ino)))
        except OSError:
            return []
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [(path, signature) for _mtime, path, signature in candidates]

    @classmethod
    def _newest_matching_file(cls, root_dir: str, scene_name: str, extensions):
        matches = cls._matching_files(root_dir, scene_name, extensions)
        return matches[0][0] if matches else None

    _to_media_rel_path = staticmethod(media_rel_path)

    @staticmethod
    def build_args(script_name, scene_name, quality, use_opengl):
        """Manim CLI arguments (everything after the executable)."""
        # A script named "-ql.py" would be parsed as an option; "./-ql.py" is a path.
        script_arg = f"./{script_name}" if script_name.startswith("-") else script_name
        args = [script_arg, scene_name, f"-q{quality}" if quality in ("l", "m", "h", "k") else "-qm"]
        if use_opengl:
            # File output is the default. --write_to_movie was removed in Manim 0.22
            # and makes the OpenGL renderer fail on every current release.
            args.append("--renderer=opengl")
        args.append("--progress_bar=display")
        return args

    def _subprocess_env(self):
        env = os.environ.copy()
        env["COLUMNS"] = SUBPROCESS_COLUMNS
        # TERM=dumb (some terminals and CI) makes Rich ignore COLUMNS and wrap at
        # 80, which splits "File ready at" paths and breaks output detection.
        env["TERM"] = "xterm-256color"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        # Manim imports the scene file; don't litter the workspace with __pycache__.
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return env

    async def _emit_file_ready(self, abs_path: str, log_callback):
        rel_path = media_rel_path(abs_path)
        filename = os.path.basename(abs_path)
        self._last_file_ready = (rel_path, filename, abs_path)
        await log_callback({
            "type": "file_ready",
            "abs_path": abs_path,
            "rel_path": rel_path,
            "filename": filename,
            "kind": output_kind(abs_path),
        })

    async def execute(self, manim_path, script_name: str, scene_name: str, quality: str, use_opengl: bool, log_callback):
        """Render *scene_name* from *script_name* and stream events to *log_callback*.

        *manim_path* is the manim executable, or an argv prefix such as
        ``[sys.executable, "-m", "manim"]``. Quality is one of l, m, h, k.
        """
        if self.is_running:
            await self.cancel()

        self._cancelled = False
        self._executing = True
        self._cancel_pending = False
        self._last_file_ready = None
        self._pending_file_ready = None
        self._latex_warned = False
        self._last_progress = None
        self.current_process = None
        # Outputs that exist before Manim starts; the disk-scan fallback ignores them.
        self._previous_outputs = self._output_snapshot(script_name, scene_name)

        prefix = list(manim_path) if isinstance(manim_path, (list, tuple)) else [manim_path]
        args = self.build_args(script_name, scene_name, quality, use_opengl)
        cmd = prefix + args
        await log_callback({"type": "info", "message": f"$ manim {' '.join(args)}"})

        popen_kwargs = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            # Manim prompts on stdin when the scene name doesn't match. Inheriting
            # the server's stdin makes that prompt wait until the render timeout.
            "stdin": asyncio.subprocess.DEVNULL,
            "cwd": self.workspace_dir,
            "env": self._subprocess_env(),
        }
        if platform.system() == "Windows":
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            # New session so cancel() can signal the whole process group (ffmpeg children).
            popen_kwargs["start_new_session"] = True

        process = None
        try:
            process = await asyncio.create_subprocess_exec(*cmd, **popen_kwargs)
            self.current_process = process
            if self._cancel_pending:
                # cancel() arrived while the process was being spawned.
                await self.cancel()

            readers = asyncio.gather(
                self._read_stream(process.stdout, "stdout", log_callback),
                self._read_stream(process.stderr, "stderr", log_callback),
            )
            try:
                await asyncio.wait_for(readers, timeout=self.render_timeout)
            except asyncio.TimeoutError:
                await log_callback({
                    "type": "error",
                    "message": f"Rendering timed out after {self.render_timeout:.0f}s.",
                })
                await self.cancel()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except Exception:
                    pass
                return {"success": False, "status": "timeout", "timeout": self.render_timeout}

            exit_code = await process.wait()

            if self._cancelled:
                await log_callback({"type": "status", "status": "cancelled", "message": "Rendering was cancelled."})
                return {"success": False, "status": "cancelled"}

            if exit_code != 0:
                await log_callback({
                    "type": "status",
                    "status": "failed",
                    "message": f"Manim exited with code {exit_code}.",
                })
                return {"success": False, "status": "failed", "exit_code": exit_code}

            if not self._last_file_ready:
                latest = self._find_latest_render(script_name, scene_name, self._previous_outputs)
                if latest:
                    await self._emit_file_ready(latest, log_callback)

            if not self._last_file_ready:
                await log_callback({
                    "type": "error",
                    "message": (
                        "Manim finished without writing a video or image. "
                        "Check that the scene name matches a Scene class in this file."
                    ),
                })
                await log_callback({
                    "type": "status",
                    "status": "failed",
                    "message": "Rendering produced no output.",
                })
                return {"success": False, "status": "failed", "exit_code": exit_code}

            await log_callback({"type": "status", "status": "success", "message": "Rendering completed successfully."})
            return {"success": True, "status": "success"}

        except Exception as exc:
            if process is not None and process.returncode is None:
                await self.cancel()
            await log_callback({"type": "error", "message": f"Executor error: {exc}"})
            return {"success": False, "status": "error", "error": str(exc)}
        finally:
            self._executing = False
            self._cancel_pending = False
            if self.current_process is process:
                self.current_process = None

    async def cancel(self):
        """Stop the active render, including ffmpeg and other child processes."""
        process = self.current_process
        if process is None or process.returncode is not None:
            if self._executing:
                self._cancel_pending = True
            return
        self._cancelled = True
        pid = process.pid
        try:
            if platform.system() == "Windows":
                kwargs = {}
                if hasattr(subprocess, "CREATE_NO_WINDOW"):
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                await asyncio.to_thread(
                    subprocess.run,
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **kwargs,
                )
            else:
                try:
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                except (ProcessLookupError, OSError):
                    process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=2)
                except (asyncio.TimeoutError, ProcessLookupError, OSError):
                    try:
                        os.killpg(os.getpgid(pid), signal.SIGKILL)
                    except (ProcessLookupError, OSError):
                        process.kill()
        except Exception:
            pass
        finally:
            # Drop the handle so a new execute() cannot race on a half-dead process.
            if self.current_process is process:
                self.current_process = None

    async def _read_stream(self, stream, stream_name, log_callback):
        """Read *stream* in chunks, splitting on both ``\\n`` and ``\\r``.

        tqdm redraws its progress bar with carriage returns and no newline, so a
        line-based reader would only see progress once an animation finished (and
        could hit StreamReader's 64 KiB line limit on long renders).
        """
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        pending = ""
        while True:
            chunk = await stream.read(READ_CHUNK_BYTES)
            if not chunk:
                break
            pending += decoder.decode(chunk)
            *lines, pending = LINE_SPLIT_PATTERN.split(pending)
            for line in lines:
                await self._handle_line(line, stream_name, log_callback)
            if len(pending) > MAX_PENDING_LINE_CHARS:
                await self._handle_line(pending, stream_name, log_callback)
                pending = ""
        pending += decoder.decode(b"", final=True)
        if pending:
            await self._handle_line(pending, stream_name, log_callback)

    def _redaction_rules(self):
        """(compiled pattern, replacement lookup) for host paths hidden from the browser.

        The workspace is removed (tracebacks show "/scene.py:5"); site-packages,
        the standard library, and the virtualenv root become ``<site-packages>``,
        ``<python-lib>``, and ``<venv>``; the temp dir ``<tmp>``; and the home
        directory ``~``. Both separator styles are matched; nothing else in the
        line is touched, so ``\\frac`` or ``C:\\Users`` typed by the user survive.
        """
        if self._redaction is not None:
            return self._redaction
        paths = sysconfig.get_paths()
        candidates = [(self.workspace_dir, "")]
        candidates += [(paths.get(key), "<site-packages>") for key in ("purelib", "platlib")]
        candidates += [(paths.get(key), "<python-lib>") for key in ("stdlib", "platstdlib")]
        if sys.prefix != sys.base_prefix:
            candidates.append((sys.prefix, "<venv>"))  # a virtualenv's own root, never /usr
        candidates += [(tempfile.gettempdir(), "<tmp>"), (os.path.expanduser("~"), "~")]
        fold = os.path.normcase("A") == "a"  # case-insensitive paths (Windows)
        lookup = {}
        for raw, replacement in candidates:
            if not raw:
                continue
            path = os.path.abspath(raw).rstrip("\\/")
            # "/" or "C:" would match far too much.
            if len(path.replace("\\", "/").strip("/")) <= 2:
                continue
            # Windows output can use either separator; POSIX paths only have "/".
            for variant in {path, path.replace("\\", "/")}:
                key = variant.lower() if fold else variant
                lookup.setdefault(key, replacement)
        if not lookup:
            self._redaction = (None, lookup)
            return self._redaction
        alternatives = "|".join(re.escape(key) for key in sorted(lookup, key=len, reverse=True))
        # A prefix only counts as a whole path: "/home/box" must not eat "/home/boxer",
        # and "/workspace" must not match inside "/srv/workspace".
        pattern = re.compile(rf"(?<![\w.\-/\\])(?:{alternatives})(?![\w.-])", re.IGNORECASE if fold else 0)
        self._redaction = (pattern, lookup)
        return self._redaction

    def _redact_paths(self, line: str) -> str:
        """Hide host paths (workspace, Python install, temp, home) in log lines sent to the browser."""
        pattern, lookup = self._redaction_rules()
        if pattern is None:
            return line
        fold = os.path.normcase("A") == "a"
        return pattern.sub(lambda match: lookup[match.group(0).lower() if fold else match.group(0)], line)

    async def _handle_line(self, raw_line: str, stream_name: str, log_callback):
        line = ANSI_PATTERN.sub("", raw_line).rstrip()
        if self._pending_file_ready:
            # A wrapped "File ready at" path continues on the next physical line.
            pending = self._pending_file_ready
            self._pending_file_ready = None
            # Lines are right-stripped, so a break right after "File ready at" lost its space.
            if line[:1].isspace() or FILE_READY_LEAD.search(pending):
                line = f"{pending.rstrip()} {line.lstrip()}"
            else:
                line = pending + line.lstrip()
        if not line.strip():
            return

        if "File ready at" in line and not line.lower().rstrip("'\"").endswith(OUTPUT_EXTENSIONS):
            self._pending_file_ready = line
            return

        bar = TQDM_PATTERN.search(line.strip())
        if bar:
            await self._emit_progress(int(bar.group("percent")), bar.group("label"), log_callback)
            return

        line = RICH_SOURCE_COLUMN.sub("", line)
        if RICH_LEVEL_ONLY.match(line.strip()):
            # The first row of a multi-line message; the text follows on the next rows.
            return

        await log_callback({"type": "log", "stream": stream_name, "message": self._redact_paths(line)})

        bracket = BRACKET_PROGRESS_PATTERN.search(line)
        if bracket:
            await self._emit_progress(int(bracket.group(1)), None, log_callback)

        file_match = FILE_READY_PATTERN.search(line)
        if file_match:
            video_path = (file_match.group("single") or file_match.group("double") or file_match.group("bare") or "").strip()
            if video_path.lower().endswith(OUTPUT_EXTENSIONS):
                abs_path = os.path.abspath(os.path.join(self.workspace_dir, video_path))
                await self._emit_file_ready(abs_path, log_callback)

        if not self._latex_warned and LATEX_PATTERN.search(line) and FAILURE_PATTERN.search(line):
            self._latex_warned = True
            await log_callback({"type": "latex_error_warning", "message": LATEX_HINT})

    async def _emit_progress(self, percent: int, label, log_callback):
        percent = max(0, min(100, percent))
        event = {"type": "progress", "percent": percent}
        animation = ANIMATION_LABEL_PATTERN.match(label.strip()) if label else None
        if animation:
            event["animation"] = int(animation.group("index"))
            event["label"] = animation.group("name").strip()
        key = (event.get("animation"), percent)
        if key == self._last_progress:
            return
        self._last_progress = key
        await log_callback(event)
