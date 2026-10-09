"""Atomic, race-safe file operations for workspace scripts.

Saves, creates, and renames of the same name are serialized by a per-name lock
(names are folded, so ``Foo.py`` and ``foo.py`` share one lock, as they share one
file on Windows and macOS). Content is written to a temporary file in the same
folder, flushed to disk, and moved into place with ``os.replace``, so a reader
sees either the old bytes or the new ones, never an empty or half-written file.
"""

from __future__ import annotations

import errno
import hashlib
import os
import tempfile
import threading
import uuid
from contextlib import ExitStack, contextmanager
from typing import Dict, Iterator

_locks: Dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()

# Temp files written by atomic_write. They never end in ".py", so the file list
# and Manim never see them; a crash can leave one behind, which the startup
# sweep removes.
TEMP_WRITE_PREFIX = ".~save-"


def content_version(data: bytes) -> str:
    """Opaque version of file content (hash of its bytes), for save-conflict checks."""
    return hashlib.sha256(data).hexdigest()[:16]


def _lock_key(path: str) -> str:
    directory, name = os.path.split(os.path.abspath(path))
    return os.path.join(os.path.normcase(directory), name.casefold())


def path_lock(path: str) -> threading.RLock:
    key = _lock_key(path)
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = _locks[key] = threading.RLock()
        return lock


@contextmanager
def locked(*paths: str) -> Iterator[None]:
    """Hold the locks of every path, always taken in the same order (no deadlocks)."""
    with ExitStack() as stack:
        for key in sorted({_lock_key(p) for p in paths}):
            with _locks_guard:
                lock = _locks.setdefault(key, threading.RLock())
            stack.enter_context(lock)
        yield


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _fsync_directory(directory: str) -> None:
    if os.name == "nt":
        return
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _new_file_mode() -> int:
    umask = os.umask(0)
    os.umask(umask)
    return 0o666 & ~umask


def _write_temp(path: str, data: bytes) -> str:
    directory = os.path.dirname(os.path.abspath(path))
    fd, temp_path = tempfile.mkstemp(prefix=TEMP_WRITE_PREFIX, suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        try:
            mode = os.stat(path).st_mode & 0o7777
        except OSError:
            mode = _new_file_mode()
        try:
            os.chmod(temp_path, mode)
        except OSError:
            pass
        return temp_path
    except BaseException:
        _unlink_quietly(temp_path)
        raise


def _unlink_quietly(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _link_supported_error(exc: OSError) -> bool:
    """True when os.link failed because the filesystem can't hard-link, not because of the target."""
    return exc.errno in {errno.EPERM, errno.EXDEV, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EMLINK, errno.ENOSYS} or (
        os.name == "nt" and getattr(exc, "winerror", None) in {1, 50}
    )


def _place_new(temp_path: str, path: str) -> None:
    """Move *temp_path* to *path* only if *path* does not exist (FileExistsError otherwise)."""
    try:
        os.link(temp_path, path)  # atomic: fails if the name exists
    except FileExistsError:
        raise
    except (AttributeError, NotImplementedError, OSError) as exc:
        if isinstance(exc, OSError) and not _link_supported_error(exc):
            raise
        # No hard links here (FAT, some network shares). Every writer of this
        # name holds its lock, so the check below cannot race another save.
        if os.path.lexists(path):
            raise FileExistsError(errno.EEXIST, "File exists", path)
        os.replace(temp_path, path)
        return
    _unlink_quietly(temp_path)


def atomic_write(path: str, data: bytes, *, exclusive: bool = False) -> str:
    """Write *data* to *path* atomically and return its version.

    The caller should hold :func:`locked` for *path* when it also checks a
    version. ``exclusive=True`` refuses to replace an existing file
    (``FileExistsError``), like ``open(path, "x")`` but without the window
    where the new file exists and is still empty.
    """
    temp_path = _write_temp(path, data)
    try:
        if exclusive:
            _place_new(temp_path, path)
        else:
            os.replace(temp_path, path)
    except BaseException:
        _unlink_quietly(temp_path)
        raise
    _fsync_directory(os.path.dirname(os.path.abspath(path)))
    return content_version(data)


def rename_no_replace(src: str, dst: str) -> None:
    """Rename *src* to *dst*, failing with FileExistsError if *dst* exists.

    Hard-link then unlink: the link fails atomically when the target exists, so
    a rename can never overwrite a file that another request just created.
    Case-only renames (``a.py`` to ``A.py``) on case-insensitive filesystems go
    through a temporary name. Take :func:`locked` for both names first.
    """
    same_file = False
    if os.path.lexists(dst):
        try:
            same_file = os.path.samefile(src, dst)
        except OSError:
            same_file = False
        if not same_file:
            raise FileExistsError(errno.EEXIST, "File exists", dst)
    if same_file:
        # Only the letter case differs and the filesystem ignores case.
        directory = os.path.dirname(os.path.abspath(src))
        hop = os.path.join(directory, f"{TEMP_WRITE_PREFIX}{uuid.uuid4().hex}.rename")
        os.rename(src, hop)
        try:
            os.rename(hop, dst)
        except BaseException:
            os.rename(hop, src)
            raise
        return
    try:
        os.link(src, dst)
    except FileExistsError:
        raise
    except (AttributeError, NotImplementedError, OSError) as exc:
        if isinstance(exc, OSError) and not _link_supported_error(exc):
            raise
        if os.path.lexists(dst):
            raise FileExistsError(errno.EEXIST, "File exists", dst)
        # os.rename refuses an existing target on Windows; elsewhere the lock and
        # the check above keep other writers of *dst* out.
        os.rename(src, dst)
        return
    try:
        os.unlink(src)
    except OSError:
        _unlink_quietly(dst)
        raise
    _fsync_directory(os.path.dirname(os.path.abspath(dst)))
