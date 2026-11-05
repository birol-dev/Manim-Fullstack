"""Workspace opt-in and background jobs for MCP's Author mode tools."""

import asyncio
from collections import deque
import json
import logging
import os
from pathlib import Path
import time
import uuid

from fastapi import HTTPException, WebSocketDisconnect

from executor import redact_host_paths
from origins import lan_enabled
from .author_preview import output_file, output_stamp


def _permission_path(workspace):
    return Path(workspace) / "studio" / "mcp-python-enabled"


def python_available():
    return not lan_enabled() and os.environ.get("RUNNING_IN_DOCKER", "").lower() != "true"


def python_enabled(workspace):
    return python_available() and _permission_path(workspace).is_file()


def set_python_enabled(workspace, enabled):
    path = _permission_path(workspace)
    if enabled:
        if not python_available():
            raise HTTPException(403, "Python authoring needs a local Studio server.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    else:
        path.unlink(missing_ok=True)


class RenderJob:
    def __init__(self, request, version, workspace, app_root):
        render_id = uuid.uuid4().hex
        self.record = {"id": render_id, "filename": request["filename"], "scene": request["scene"],
                       "version": version, "status": "queued", "progress": 0}
        self.workspace = workspace
        self.app_root = app_root
        self.logs = deque(maxlen=30)
        self.output_stamp = None
        self.messages = asyncio.Queue()
        self.messages.put_nowait(json.dumps({**request, "type": "start", "id": render_id}, ensure_ascii=False))
        self.closed = False
        self.task = None

    async def receive(self):
        message = await self.messages.get()
        if message is None:
            raise WebSocketDisconnect()
        return message

    async def send(self, text):
        event = json.loads(text)
        kind = event["type"]
        if kind == "queued":
            self.record.update(status="queued", position=event["position"])
        elif kind == "started" or kind == "progress" or event.get("status") == "rendering":
            self.record.update(status="rendering", position=0)
            if kind == "progress":
                self.record["progress"] = event["percent"]
        elif kind == "file_ready":
            self.record["output"] = {key: event[key] for key in ("url", "filename", "kind")}
            try:
                self.output_stamp = output_stamp(output_file(self.workspace, event["url"]))
            except (OSError, RuntimeError):
                self.output_stamp = None
        elif kind == "result":
            self.record.update(status="done" if event["success"] else event["status"], position=0)
            if event["success"]:
                self.record["progress"] = 100
            self.close()
        if kind in ("log", "error") and event.get("message"):
            self.logs.append(redact_host_paths(event["message"], self.workspace, self.app_root)[-1500:])

    def close(self):
        if not self.closed:
            self.closed = True
            self.messages.put_nowait(None)

    def view(self):
        return {**self.record, "logs": list(self.logs)}


class RenderJobs:
    def __init__(self):
        self.jobs = {}
        self.writes = deque(maxlen=32)

    def script_saved(self, filename, version):
        self.writes.appendleft({"id": uuid.uuid4().hex, "kind": "script", "filename": filename,
                                "version": version, "started_at": time.time()})

    def activity(self):
        renders = [{**job.record, "kind": "render"} for job in self.jobs.values()]
        return sorted([*self.writes, *renders], key=lambda item: item["started_at"], reverse=True)[:32]

    def start(self, session, request, version, workspace, app_root):
        if len(self.jobs) >= 64:
            oldest_finished = next((key for key, job in self.jobs.items() if job.task.done()), None)
            if oldest_finished is None:
                raise HTTPException(429, "Too many Python renders are pending.")
            del self.jobs[oldest_finished]
        job = RenderJob(request, version, workspace, app_root)
        job.record["started_at"] = time.time()
        self.jobs[job.record["id"]] = job
        job.task = asyncio.create_task(self._run(session, job))
        return job.view()

    async def _run(self, session, job):
        try:
            await session(job.receive, job.send)
        except Exception:
            logging.getLogger(__name__).exception("Python render session failed")
            job.logs.append("The render session stopped unexpectedly.")
        finally:
            if job.record["status"] in ("queued", "rendering"):
                job.record.update(status="error", position=0)

    def get(self, render_id):
        job = self.jobs.get(render_id)
        if job is None:
            raise HTTPException(404, "Python render not found in this Studio session.")
        return job

    def active(self):
        return any(not job.task.done() for job in self.jobs.values())

    async def cancel(self, render_id):
        job = self.get(render_id)
        job.close()
        await asyncio.shield(job.task)
        return job.view()

    async def stop(self):
        active = [job for job in self.jobs.values() if not job.task.done()]
        for job in active:
            job.close()
        await asyncio.gather(*(job.task for job in active))
