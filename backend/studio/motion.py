"""On-demand motion previews, isolated from the export queue and still worker."""
from __future__ import annotations

from collections import deque
import copy
import json
import logging
import os
import secrets
import threading

from .errors import BusyError, NotFoundError
from .storage import TEMP_MARK, prune_previews
from .worker import WorkerCancelled

MAX_DURATION = 20
LONG_SIDE = 720
FPS = 15
logger = logging.getLogger("studio")


class MotionPreviews:
    def __init__(self, service, worker):
        self.service, self.worker = service, worker
        self.condition = threading.Condition(threading.RLock())
        self.records = {}
        self.waiting = deque()
        self.closing = False
        self.kit = None
        self.thread = threading.Thread(target=self._run, name="studio-motion", daemon=True)
        self.thread.start()

    @staticmethod
    def public(record):
        return copy.deepcopy({k: v for k, v in record.items() if not k.startswith("_")})

    def start(self, project, job, width, height, key):
        path = os.path.join(self.service.previews_dir, key + ".mp4")
        with self.condition:
            for record in self.records.values():
                if record["project"] == project and record["status"] in ("queued", "rendering"):
                    record["_cancel"].set()
                    record["status"] = "cancelled"
            # Bound queue/history even if a client keeps requesting new previews.
            for rid in list(self.records):
                if len(self.records) < 100:
                    break
                if self.records[rid]["status"] not in ("queued", "rendering"):
                    del self.records[rid]
            if len(self.records) >= 100:
                raise BusyError("Too many previews waiting. Try again in a moment.")
            record = {"id": secrets.token_hex(8), "project": project, "status": "queued", "mode": "motion",
                      "width": width, "height": height, "fps": FPS, "max_duration": MAX_DURATION,
                      "cached": False, "_job": job, "_path": path, "_cancel": threading.Event()}
            try:
                with open(os.path.splitext(path)[0] + ".json", encoding="utf-8") as source:
                    meta = json.load(source)
                if os.path.isfile(path):
                    record.update(status="done", cached=True, url=self.service._media_url(path),
                                  duration=meta["duration"], truncated=meta["truncated"])
                    os.utime(path)
            except (OSError, ValueError, KeyError):
                pass
            self.records[record["id"]] = record
            if record["status"] == "queued":
                self.waiting.append(record)
                self.condition.notify()
            return self.public(record)

    def get(self, rid):
        with self.condition:
            if rid not in self.records:
                raise NotFoundError("That preview is no longer available. Make a new preview.")
            return self.public(self.records[rid])

    def cancel(self, rid):
        with self.condition:
            self.get(rid)
            record = self.records[rid]
            if record["status"] in ("queued", "rendering"):
                record["_cancel"].set()
                record["status"] = "cancelled"
            return self.public(record)

    def close(self):
        with self.condition:
            self.closing = True
            for record in self.records.values():
                record["_cancel"].set()
            self.condition.notify()
        self.worker.close()
        self.thread.join(timeout=5)

    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.closing or self.waiting)
                if self.closing:
                    return
                record = self.waiting.popleft()
                if record["_cancel"].is_set():
                    continue
                record["status"] = "rendering"
            stem = os.path.join(self.service.previews_dir, TEMP_MARK + record["id"])
            try:
                os.makedirs(self.service.previews_dir, exist_ok=True)
                kit = self.service._kit_fingerprint()
                if self.kit is not None and kit != self.kit:
                    self.worker.stop()
                self.kit = kit
                result = self.worker.render({**record["_job"], "mode": "motion", "output": stem + ".mp4",
                                             "max_duration": MAX_DURATION}, record["width"], record["height"],
                                            timeout=max(120, self.service.preview_timeout), cancel=record["_cancel"])
                with self.condition:
                    if record["_cancel"].is_set():
                        continue
                    meta = {"duration": result["duration"], "truncated": result["truncated"]}
                    with open(stem + ".json", "w", encoding="utf-8") as target:
                        json.dump(meta, target)
                    os.replace(stem + ".mp4", record["_path"])
                    os.replace(stem + ".json", os.path.splitext(record["_path"])[0] + ".json")
                    record.update(status="done", url=self.service._media_url(record["_path"]), **meta)
                prune_previews(self.service.previews_dir, self.service.cache_limit)
            except WorkerCancelled:
                with self.condition:
                    record["status"] = "cancelled"
            except Exception:  # failures never kill the dispatcher
                logger.exception("studio: motion preview failed (%s)", record["id"])
                with self.condition:
                    if not record["_cancel"].is_set():
                        record.update(status="failed", error="Couldn't make a quick preview. Please try again.")
            finally:
                for extension in (".mp4", ".json"):
                    try:
                        os.unlink(stem + extension)
                    except OSError:
                        pass
