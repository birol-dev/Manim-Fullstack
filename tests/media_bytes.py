"""Smallest byte strings that pass executor.media_file_is_complete() per output type."""

import os

MP4 = b"\x00\x00\x00\x10ftypisom\x00\x00\x02\x00" + b"\x00\x00\x00\x08moov" + b"\x00\x00\x00\x0cmdatdata"
# What an interrupted encode leaves: header boxes, no moov.
MP4_BROKEN = b"\x00\x00\x00\x10ftypisom\x00\x00\x02\x00" + b"\x00\x00\x00\x00mdat" + b"x" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16 + b"\x00\x00\x00\x00IEND\xaeB`\x82"
GIF = b"GIF89a" + b"\x00" * 16 + b"\x3b"
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 80


def valid_bytes(name: str) -> bytes:
    ext = os.path.splitext(str(name))[1].lower()
    return {".png": PNG, ".gif": GIF, ".webm": WEBM}.get(ext, MP4)


def write_media(path, data=None, mtime=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(valid_bytes(path.name) if data is None else data)
    if mtime is not None:
        os.utime(str(path), (mtime, mtime))
    return path
