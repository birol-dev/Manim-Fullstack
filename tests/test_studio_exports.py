"""Forgetting export history preserves files, including files in batch folders."""

import json

import pytest

from studio.errors import NotFoundError
from studio.exports import ExportManager


@pytest.mark.parametrize("status", ["done", "failed", "cancelled"])
@pytest.mark.parametrize("folder", [None, "a-batch"])
def test_forget_persists_record_removal_and_never_deletes_the_file(tmp_path, status, folder):
    exports = tmp_path / "exports"
    output = exports / folder if folder else exports
    output.mkdir(parents=True)
    video = output / "my-video.mp4"
    video.write_bytes(b"saved video")
    index = tmp_path / "exports.json"
    record = {"id": "012345abcdef", "status": status, "filename": video.name, "created": "1"}
    if folder:
        record["folder"] = folder
    index.write_text(json.dumps({"exports": [record]}), encoding="utf-8")

    def manager():
        return ExportManager(exports_dir=str(exports), work_dir=str(tmp_path / "work"),
                             index_path=str(index), media_root=str(tmp_path),
                             plan=None, still=None, runner_factory=None)

    history = manager()
    assert history.forget(record["id"]) == {**record, "time_left": None}
    assert video.read_bytes() == b"saved video"
    assert history.list() == []
    assert manager().list() == []  # the record stays forgotten after a restart
    with pytest.raises(NotFoundError):
        history.get(record["id"])
    assert video.read_bytes() == b"saved video"
