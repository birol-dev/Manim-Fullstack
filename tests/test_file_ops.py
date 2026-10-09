"""file_ops: atomic writes, exclusive creates, no-replace renames, and per-name locks."""

import errno
import os
import threading

import pytest

import file_ops
from file_ops import atomic_write, content_version, locked, path_lock, read_bytes, rename_no_replace


def test_atomic_write_returns_the_version_of_the_bytes_written(tmp_path):
    target = tmp_path / "a.py"
    version = atomic_write(str(target), b"x = 1\n")
    assert version == content_version(b"x = 1\n")
    assert target.read_bytes() == b"x = 1\n"
    # No temp file is left next to it.
    assert [p.name for p in tmp_path.iterdir()] == ["a.py"]


def test_atomic_write_keeps_the_file_mode(tmp_path):
    target = tmp_path / "a.py"
    target.write_bytes(b"old")
    os.chmod(target, 0o640)
    atomic_write(str(target), b"new")
    assert (os.stat(target).st_mode & 0o777) == 0o640


def test_new_files_get_the_usual_umask_mode(tmp_path):
    target = tmp_path / "n.py"
    atomic_write(str(target), b"x")
    umask = os.umask(0)
    os.umask(umask)
    assert (os.stat(target).st_mode & 0o777) == (0o666 & ~umask)


def test_exclusive_write_never_replaces(tmp_path):
    target = tmp_path / "a.py"
    target.write_bytes(b"theirs")
    with pytest.raises(FileExistsError):
        atomic_write(str(target), b"mine", exclusive=True)
    assert target.read_bytes() == b"theirs"
    assert [p.name for p in tmp_path.iterdir()] == ["a.py"]


def test_exclusive_write_without_hard_links_still_refuses_existing(tmp_path, monkeypatch):
    def no_links(*_args):
        raise OSError(errno.EPERM, "Operation not permitted")

    monkeypatch.setattr(os, "link", no_links)
    target = tmp_path / "a.py"
    assert atomic_write(str(target), b"one", exclusive=True) == content_version(b"one")
    with pytest.raises(FileExistsError):
        atomic_write(str(target), b"two", exclusive=True)
    assert target.read_bytes() == b"one"


def test_write_failure_leaves_no_temp_file(tmp_path, monkeypatch):
    def boom(*_args):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        atomic_write(str(tmp_path / "a.py"), b"data")
    assert list(tmp_path.iterdir()) == []


def test_rename_no_replace(tmp_path):
    src, dst = tmp_path / "a.py", tmp_path / "b.py"
    src.write_bytes(b"A")
    rename_no_replace(str(src), str(dst))
    assert not src.exists() and dst.read_bytes() == b"A"

    src.write_bytes(b"new A")
    with pytest.raises(FileExistsError):
        rename_no_replace(str(src), str(dst))
    assert src.read_bytes() == b"new A" and dst.read_bytes() == b"A"


def test_rename_no_replace_without_hard_links(tmp_path, monkeypatch):
    def no_links(*_args):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(os, "link", no_links)
    src, dst = tmp_path / "a.py", tmp_path / "b.py"
    src.write_bytes(b"A")
    dst.write_bytes(b"B")
    with pytest.raises(FileExistsError):
        rename_no_replace(str(src), str(dst))
    dst.unlink()
    rename_no_replace(str(src), str(dst))
    assert dst.read_bytes() == b"A"


def test_other_link_errors_are_not_hidden(tmp_path, monkeypatch):
    def denied(*_args):
        raise OSError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(os, "link", denied)
    (tmp_path / "a.py").write_bytes(b"A")
    with pytest.raises(PermissionError):
        rename_no_replace(str(tmp_path / "a.py"), str(tmp_path / "b.py"))


def test_case_only_rename_on_a_case_insensitive_filesystem(tmp_path, monkeypatch):
    """When both names are the same file, the rename hops through a temporary name."""
    src = tmp_path / "a.py"
    src.write_bytes(b"A")
    dst = tmp_path / "A.py"
    monkeypatch.setattr(os.path, "samefile", lambda a, b: True)
    real_lexists = os.path.lexists
    monkeypatch.setattr(os.path, "lexists", lambda p: True if p == str(dst) else real_lexists(p))
    rename_no_replace(str(src), str(dst))
    assert dst.read_bytes() == b"A" and not src.exists()
    assert not any(p.name.startswith(file_ops.TEMP_WRITE_PREFIX) for p in tmp_path.iterdir())


def test_locks_fold_case(tmp_path):
    assert path_lock(str(tmp_path / "Foo.py")) is path_lock(str(tmp_path / "foo.py"))
    assert path_lock(str(tmp_path / "foo.py")) is not path_lock(str(tmp_path / "bar.py"))


def test_locked_takes_several_names_in_a_fixed_order(tmp_path):
    a, b = str(tmp_path / "a.py"), str(tmp_path / "b.py")
    done = []

    def one():
        for _ in range(200):
            with locked(a, b):
                pass
        done.append(1)

    def other():
        for _ in range(200):
            with locked(b, a):
                pass
        done.append(2)

    threads = [threading.Thread(target=one), threading.Thread(target=other)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert sorted(done) == [1, 2]  # no deadlock


def test_readers_never_see_partial_content(tmp_path):
    target = tmp_path / "big.py"
    contents = [b"a" * 400_000, b"b" * 300_000]
    atomic_write(str(target), contents[0])
    stop = threading.Event()
    seen = {"bad": 0, "ok": 0}

    def writer():
        i = 0
        while not stop.is_set():
            atomic_write(str(target), contents[i % 2])
            i += 1

    def reader():
        while not stop.is_set():
            data = read_bytes(str(target))
            seen["ok" if data in contents else "bad"] += 1

    threads = [threading.Thread(target=writer)] + [threading.Thread(target=reader) for _ in range(2)]
    for t in threads:
        t.start()
    threading.Event().wait(1.0)
    stop.set()
    for t in threads:
        t.join()
    assert seen["bad"] == 0 and seen["ok"] > 0
