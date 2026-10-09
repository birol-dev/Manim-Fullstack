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
import functools
import os
import platform
import re
import signal
import subprocess
import sys
import sysconfig
import tempfile
import time
import unicodedata

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
# A source line quoted in a Rich traceback: "│ ❱ 12 │ code" (the user's own code).
RICH_CODE_LINE = re.compile(r"^[│┃]\s+(?:❱\s+)?\d+\s+[│┃]")
# One row of a Rich box: "│ text │".
BOX_LINE = re.compile(r"^(?P<left>[│┃] )(?P<body>.*?)(?P<right> [│┃])$")
MAX_BOX_CHAIN = 32
# A "File ready at" output older than the run start (minus this, for coarse
# filesystem timestamps) is not this run's output.
FILE_READY_MTIME_SLACK_NS = 2_000_000_000
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


def cell_len(text: str) -> int:
    """Terminal cells *text* takes up (CJK and emoji are two wide), as Rich counts them."""
    try:
        from rich.cells import cell_len as rich_cell_len
    except ImportError:  # Rich ships with Manim; the API can run without it
        width = 0
        for ch in text:
            if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me", "Cf"):
                continue
            width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        return width
    return rich_cell_len(text)


BOX_BORDERS = ("│", "┃")


def keep_box_width(original: str, changed: str) -> str:
    """Keep the right border of a boxed Rich traceback line where it was.

    A shorter line is padded before the border; a longer one gives back spaces
    from the padding (keeping one). Widths are terminal cells, so CJK counts double.
    """
    if not changed.endswith(BOX_BORDERS) or not original.endswith(BOX_BORDERS):
        return changed
    delta = cell_len(original) - cell_len(changed)
    if delta > 0:
        return changed[:-1] + " " * delta + changed[-1]
    if delta < 0:
        body = changed[:-1]
        spare = len(body) - len(body.rstrip(" ")) - 1
        take = min(max(spare, 0), -delta)
        if take:
            return body[: len(body) - take] + changed[-1]
    return changed


# Hosts paths are replaced by these markers before log lines reach the browser.
WORKSPACE_MARKER = "<workspace>"
APP_MARKER = "<app>"


def _redaction_candidates(workspace_dir, app_root):
    """(path, replacement) pairs; the workspace with a separator becomes "" (relative paths)."""
    paths = sysconfig.get_paths()
    candidates = [(workspace_dir, WORKSPACE_MARKER)]
    candidates += [(paths.get(key), "<site-packages>") for key in ("purelib", "platlib")]
    candidates += [(paths.get(key), "<python-lib>") for key in ("stdlib", "platstdlib")]
    if sys.prefix != sys.base_prefix:
        candidates.append((sys.prefix, "<venv>"))  # a virtualenv's own root, never /usr
    if app_root:
        candidates.append((app_root, APP_MARKER))
    candidates += [(tempfile.gettempdir(), "<tmp>"), (os.path.expanduser("~"), "~")]
    return candidates


@functools.lru_cache(maxsize=32)
def _compile_redaction(workspace_dir, app_root, home, tmp):
    del home, tmp  # cache keys only: rules change when HOME or TMPDIR change
    fold = os.path.normcase("A") == "a"  # case-insensitive paths (Windows)
    lookup = {}
    with_separator = set()
    for raw, replacement in _redaction_candidates(workspace_dir, app_root):
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
            if replacement == WORKSPACE_MARKER:
                # "<workspace>/scene.py" becomes "scene.py"; the bare folder "<workspace>".
                for sep in {os.sep, "/"}:
                    with_separator.add(key + sep)
                    lookup.setdefault(key + sep, "")
    if not lookup:
        return None, lookup

    def alternation(keys):
        return "|".join(re.escape(key) for key in sorted(keys, key=len, reverse=True))

    plain = [key for key in lookup if key not in with_separator]
    # A whole path only: "/home/box" must not eat "/home/boxer" or "/home/box.bak",
    # but a sentence may end right after it ("saved in /home/box.").
    whole = rf"(?:{alternation(plain)})(?![\w-]|\.[\w-])"
    if with_separator:
        whole = rf"(?:{alternation(with_separator)})|{whole}"
    # ...and must start a path: "/workspace" inside "/srv/workspace" is left alone,
    # except right after a file:// scheme.
    start = r"(?:(?<=file://)|(?<=file:///)|(?<![\w.\-/\\]))"
    pattern = re.compile(rf"{start}(?:{whole})", re.IGNORECASE if fold else 0)
    return pattern, lookup


def _redaction_for(workspace_dir, app_root=None):
    return _compile_redaction(
        os.path.abspath(workspace_dir) if workspace_dir else "",
        os.path.abspath(app_root) if app_root else None,
        os.path.expanduser("~"),
        tempfile.gettempdir(),
    )


def redact_with_offsets(text: str, workspace_dir, app_root=None):
    """Redact *text*; also return a function mapping an index in *text* to the output.

    An index inside a replaced path maps to the end of its replacement.
    """
    pattern, lookup = _redaction_for(workspace_dir, app_root)
    if pattern is None:
        return text, (lambda index: index)
    fold = os.path.normcase("A") == "a"
    pieces = []
    spans = []  # (start, end, out_end)
    last = 0
    length = 0
    for match in pattern.finditer(text):
        pieces.append(text[last:match.start()])
        length += match.start() - last
        replacement = lookup[match.group(0).lower() if fold else match.group(0)]
        if replacement == "" and text[max(0, match.start() - 7):match.start()].lower() in ("file://", "ile:///"):
            replacement = WORKSPACE_MARKER + "/"  # "file://scene.py" would not be a URI
        pieces.append(replacement)
        length += len(replacement)
        spans.append((match.start(), match.end(), length))
        last = match.end()
    pieces.append(text[last:])
    out = "".join(pieces)

    def mapped(index: int) -> int:
        shift = 0
        for start, end, out_end in spans:
            if index <= start:
                break
            if index < end:
                return out_end
            shift = out_end - end
        return index + shift

    return out, mapped


def redact_host_paths(text: str, workspace_dir, app_root=None) -> str:
    """Hide host paths (workspace, app folder, Python install, temp, home) in *text*."""
    return redact_with_offsets(text, workspace_dir, app_root)[0]


def output_kind(path: str) -> str:
    """Return ``"image"`` or ``"video"`` for a rendered output path."""
    return "image" if path.lower().endswith(IMAGE_EXTENSIONS) else "video"


class ManimExecutor:
    def __init__(self, workspace_dir: str, render_timeout=None, app_root=None):
        self.workspace_dir = workspace_dir
        # The folder the app lives in (the workspace's parent); shown as <app>.
        self.app_root = app_root
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
        self._box_carry = {}
        self._output_stem = None
        self._hidden_config = None
        self._run_started_ns = 0

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

    async def execute(
        self,
        manim_path,
        script_name: str,
        scene_name: str,
        quality: str,
        use_opengl: bool,
        log_callback,
        output_stem=None,
        extra_args=None,
    ):
        """Render *scene_name* from *script_name* and stream events to *log_callback*.

        *manim_path* is the manim executable, or an argv prefix such as
        ``[sys.executable, "-m", "manim"]``. Quality is one of l, m, h, k.
        *output_stem* is the media folder the output lands in when it differs
        from the script's own stem (a snapshot rendered with a per-run config);
        *extra_args* are passed to Manim but not shown in the command echo.
        """
        output_stem = output_stem or os.path.splitext(script_name)[0]
        if self.is_running:
            await self.cancel()

        self._cancelled = False
        self._executing = True
        self._cancel_pending = False
        self._last_file_ready = None
        self._pending_file_ready = None
        self._latex_warned = False
        self._last_progress = None
        self._box_carry = {}
        self.current_process = None
        output_name = output_stem + ".py"
        # Outputs that exist before Manim starts; the disk-scan fallback ignores them.
        self._previous_outputs = self._output_snapshot(output_name, scene_name)

        prefix = list(manim_path) if isinstance(manim_path, (list, tuple)) else [manim_path]
        args = self.build_args(script_name, scene_name, quality, use_opengl)
        cmd = prefix + args + list(extra_args or [])
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
        self._output_stem = output_stem
        args_list = list(extra_args or [])
        self._hidden_config = (
            os.path.basename(args_list[args_list.index("--config_file") + 1])
            if "--config_file" in args_list[:-1] else None
        )
        self._run_started_ns = time.time_ns()
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
                latest = self._find_latest_render(output_name, scene_name, self._previous_outputs)
                if latest and self._trusted_output(latest):
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
            self._output_stem = None
            self._hidden_config = None
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
            while len(pending) > MAX_PENDING_LINE_CHARS:
                # Cut an endless line at a space, so a path is never split in two
                # (each half would slip past redaction).
                cut = max(pending.rfind(" ", 0, MAX_PENDING_LINE_CHARS), pending.rfind("\t", 0, MAX_PENDING_LINE_CHARS))
                if cut < MAX_PENDING_LINE_CHARS // 2:
                    cut = MAX_PENDING_LINE_CHARS
                await self._handle_line(pending[:cut], stream_name, log_callback)
                pending = pending[cut:]
        pending += decoder.decode(b"", final=True)
        if pending:
            await self._handle_line(pending, stream_name, log_callback)
        await self._flush_box_carry(stream_name, log_callback)

    def _redaction_rules(self):
        """(compiled pattern, replacement lookup) for host paths hidden from the browser.

        The workspace prefix and its separator are removed, so paths come out
        relative ("scene.py:5", "media/videos/..."), and the bare workspace folder
        becomes ``<workspace>``; the app folder ``<app>``; site-packages, the
        standard library, and the virtualenv root ``<site-packages>``,
        ``<python-lib>``, and ``<venv>``; the temp dir ``<tmp>``; and the home
        directory ``~``. Both separator styles are matched; nothing else in the
        line is touched, so ``\\frac`` or ``C:\\Users`` typed by the user survive.
        """
        return _redaction_for(self.workspace_dir, self.app_root)

    def _redact_paths(self, line: str) -> str:
        """Hide host paths in a log line sent to the browser.

        Source lines quoted in a Rich traceback (``│ ❱ 12 │ x = "/tmp/a"``) are
        the user's own code and are left exactly as written.
        """
        if RICH_CODE_LINE.match(line):
            return line
        redacted = redact_host_paths(line, self.workspace_dir, self.app_root)
        return keep_box_width(line, redacted)

    @staticmethod
    def _box_word(line: str):
        """The match for a boxed Rich line filled edge to edge by one word (a wrapped path)."""
        match = BOX_LINE.match(line)
        if match and match.group("body") and not any(ch.isspace() for ch in match.group("body")):
            return match
        return None

    def _rejoin_box_lines(self, lines):
        """Redact a path that Rich folded over several boxed lines, keeping the box.

        The pieces are joined, redacted as one path, and folded again to the
        box width.
        """
        parts = [BOX_LINE.match(line) for line in lines]
        if any(part is None for part in parts):
            return [self._redact_paths(line) for line in lines]
        width = cell_len(parts[0].group("body"))
        bodies = [part.group("body") for part in parts[:-1]] + [parts[-1].group("body").rstrip()]
        joined = "".join(bodies)
        redacted = redact_with_offsets(joined, self.workspace_dir, self.app_root)[0]
        if redacted == joined:
            return [self._redact_paths(line) for line in lines]
        # Rich folded one long word, so the breaks carry no meaning: fold the
        # redacted text again. Only " in <function>" after a frame path is a real
        # word break, and it stays on its own line.
        tail = None
        if len(bodies) > 1 and bodies[-1].startswith("in "):
            tail = bodies[-1]
            folded = redact_with_offsets("".join(bodies[:-1]), self.workspace_dir, self.app_root)[0]
        else:
            folded = redacted
        left, right = parts[0].group("left"), parts[0].group("right")
        out = []
        for segment in ([folded, tail] if tail is not None else [folded]):
            while segment:
                piece = segment
                while cell_len(piece) > width:
                    piece = piece[:-1]
                if piece != segment and " " in piece.strip():
                    # Real words ("in boom") wrap at a space, as Rich would.
                    piece = piece[: piece.rstrip().rindex(" ") + 1]
                segment = segment[len(piece):].lstrip(" ") if piece != segment else ""
                piece = piece.rstrip(" ") or piece
                out.append(left + piece + " " * max(width - cell_len(piece), 0) + right)
        return out or [self._redact_paths(line) for line in lines]

    async def _flush_box_carry(self, stream_name, log_callback):
        carry = self._box_carry.pop(stream_name, None)
        if carry:
            for line in carry:
                await self._process_line(line, stream_name, log_callback)

    def _trusted_output(self, abs_path: str) -> bool:
        """A "File ready at" path counts only if this run could have written it.

        It must resolve inside this script's own media folders and be modified
        at or after the render started; user code printing a fake line pointing
        at an older video (or anything else on disk) is ignored.
        """
        if self._output_stem is None:
            return True  # not inside execute(): unit tests feeding lines directly
        try:
            real = os.path.realpath(abs_path)
            info = os.stat(real)
        except OSError:
            return False
        if not os.path.isfile(real):
            return False
        inside = False
        for subdir in ("videos", "images"):
            root = os.path.realpath(os.path.join(self.workspace_dir, "media", subdir, self._output_stem))
            if os.path.normcase(real).startswith(os.path.normcase(root) + os.sep):
                inside = True
                break
        if not inside:
            return False
        return info.st_mtime_ns >= self._run_started_ns - FILE_READY_MTIME_SLACK_NS

    async def _handle_line(self, raw_line: str, stream_name: str, log_callback):
        line = ANSI_PATTERN.sub("", raw_line).rstrip()
        carry = self._box_carry.get(stream_name)
        if carry is not None:
            if BOX_LINE.match(line) and len(carry) < MAX_BOX_CHAIN:
                carry.append(line)
                if self._box_word(line):
                    return  # the folded path goes on
                del self._box_carry[stream_name]
                for joined in self._rejoin_box_lines(carry):
                    await self._process_line(joined, stream_name, log_callback, redacted=True)
                return
            await self._flush_box_carry(stream_name, log_callback)
        if self._box_word(line):
            self._box_carry[stream_name] = [line]
            return
        await self._process_line(line, stream_name, log_callback)

    async def _process_line(self, line: str, stream_name: str, log_callback, redacted: bool = False):
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
        if self._hidden_config and "Reading config file" in line and self._hidden_config in line:
            return  # the per-run config is an internal detail, like the scratch script

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

        message = line if redacted else self._redact_paths(line)
        await log_callback({"type": "log", "stream": stream_name, "message": message})

        bracket = BRACKET_PROGRESS_PATTERN.search(line)
        if bracket:
            await self._emit_progress(int(bracket.group(1)), None, log_callback)

        file_match = FILE_READY_PATTERN.search(line)
        if file_match:
            video_path = (file_match.group("single") or file_match.group("double") or file_match.group("bare") or "").strip()
            if video_path.lower().endswith(OUTPUT_EXTENSIONS):
                abs_path = os.path.abspath(os.path.join(self.workspace_dir, video_path))
                if self._trusted_output(abs_path):
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
