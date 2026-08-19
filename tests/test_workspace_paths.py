import os
from pathlib import Path
from unittest.mock import patch
import pytest

from workspace_paths import (
    WINDOWS_RESERVED_NAMES,
    UnsafePathError,
    is_within_directory,
    safe_basename,
    safe_join,
)


def test_accepts_plain_python_filename():
    assert safe_basename("example.py", required_suffix=".py") == "example.py"


def test_rejects_parent_directory_traversal():
    with pytest.raises(UnsafePathError):
        safe_basename("../secret.py", required_suffix=".py")


def test_rejects_nested_relative_path():
    with pytest.raises(UnsafePathError):
        safe_basename("subdir/scene.py", required_suffix=".py")


@pytest.mark.parametrize("name", ["", "   ", ".", "..", None])
def test_rejects_empty_and_dot_names(name):
    with pytest.raises(UnsafePathError):
        safe_basename(name)


def test_rejects_backslash_traversal():
    with pytest.raises(UnsafePathError):
        safe_basename("..\\secret.py", required_suffix=".py")


def test_rejects_wrong_suffix():
    with pytest.raises(UnsafePathError):
        safe_basename("notes.txt", required_suffix=".py")


@pytest.mark.parametrize("reserved", sorted(WINDOWS_RESERVED_NAMES))
def test_rejects_windows_reserved_device_names(reserved):
    with pytest.raises(UnsafePathError):
        safe_basename(f"{reserved.lower()}.py", required_suffix=".py")
    with pytest.raises(UnsafePathError):
        safe_basename(f"{reserved.upper()}.mp4")


@pytest.mark.parametrize("name", ["test.py.", "test.py ", " test.py", "asset.svg.", "asset.png "])
def test_rejects_trailing_leading_dots_and_spaces(name):
    with pytest.raises(UnsafePathError):
        safe_basename(name)


@pytest.mark.parametrize("name", ["/etc/passwd", "/root/secret.py", "C:/autoexec.bat", "D:\\secret.py"])
def test_rejects_absolute_paths_unix_and_windows(name):
    with pytest.raises(UnsafePathError):
        safe_basename(name)


def test_rejects_null_byte_in_filename():
    with pytest.raises(UnsafePathError):
        safe_basename("valid\x00name.py")


def test_rejects_sibling_prefix_directory(tmp_path):
    media_dir = tmp_path / "media"
    sibling = tmp_path / "media_backup"
    media_dir.mkdir()
    sibling.mkdir()
    secret = sibling / "secret.mp4"
    secret.write_text("secret_content", encoding="utf-8")

    assert is_within_directory(str(media_dir / "clip.mp4"), str(media_dir))
    assert not is_within_directory(str(secret), str(media_dir))
    with pytest.raises(UnsafePathError):
        safe_join(str(media_dir), os.path.join("..", "media_backup", "secret.mp4"))


def test_rejects_absolute_path_join(tmp_path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    outside = tmp_path / "outside.mp4"
    outside.write_text("x", encoding="utf-8")

    with pytest.raises(UnsafePathError):
        safe_join(str(media_dir), str(outside))


def test_safe_join_keeps_relative_media_path(tmp_path):
    media_dir = tmp_path / "media"
    videos_dir = media_dir / "videos"
    videos_dir.mkdir(parents=True)

    joined = safe_join(str(media_dir), "videos", "scene.mp4")
    assert is_within_directory(joined, str(media_dir))
    assert joined.endswith(os.path.join("videos", "scene.mp4"))


def test_is_within_directory_handles_os_errors():
    with patch("pathlib.Path.resolve", side_effect=OSError("Disk failure")):
        assert not is_within_directory("/any/path", "/any/dir")
