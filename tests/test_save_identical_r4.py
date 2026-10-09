"""R4 #7: a stale base_version whose content already matches the disk is not a conflict."""
import os
from unittest.mock import patch

import main


def _open(client, name):
    res = client.get(f"/api/file-content?filename={name}")
    assert res.status_code == 200
    return res.json()


def test_stale_version_with_identical_content_succeeds_without_writing(client, tmp_path):
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)):
        path = tmp_path / "same.py"
        path.write_text("x = 1\n", encoding="utf-8")
        stale = _open(client, "same.py")["version"]
        # Changed outside the app (an editor) to exactly what this tab is about to save.
        path.write_text("x = 2\n", encoding="utf-8")
        os.utime(path, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
        current = _open(client, "same.py")["version"]
        assert current != stale
        mtime = path.stat().st_mtime_ns

        res = client.post("/api/save", json={"filename": "same.py", "code": "x = 2\n", "base_version": stale})
        assert res.status_code == 200, res.text
        body = res.json()
        # The client continues from the version on disk; nothing was rewritten.
        assert body["version"] == current
        assert path.stat().st_mtime_ns == mtime
        assert path.read_text(encoding="utf-8") == "x = 2\n"


def test_stale_version_with_different_content_is_still_a_conflict(client, tmp_path):
    with patch.object(main, "WORKSPACE_DIR", str(tmp_path)):
        path = tmp_path / "diff.py"
        path.write_text("x = 1\n", encoding="utf-8")
        stale = _open(client, "diff.py")["version"]
        path.write_text("x = 2\n", encoding="utf-8")
        os.utime(path, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
        res = client.post("/api/save", json={"filename": "diff.py", "code": "x = 3\n", "base_version": stale})
        assert res.status_code == 412
        assert path.read_text(encoding="utf-8") == "x = 2\n"
