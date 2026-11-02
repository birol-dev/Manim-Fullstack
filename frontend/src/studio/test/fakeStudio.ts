import { vi } from "vitest";

import type { Catalog, ExportJob, PreviewRequest, Project } from "../types";
import { CATALOG } from "./fixtures";

export interface Call {
  method: string;
  path: string;
  body: unknown;
}

export interface FakeStudio {
  calls: Call[];
  catalog: Catalog;
  projects: Project[];
  exports: ExportJob[];
  /** Answer a preview with this instead of an image (e.g. a 422). */
  previewReply: ((request: PreviewRequest) => { status: number; body: unknown } | null) | null;
  reply: ((call: Call) => { status: number; body: unknown } | null | Promise<{ status: number; body: unknown } | null>) | null;
  previews: () => PreviewRequest[];
}

function reply(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ "Content-Type": "application/json" }),
    json: async () => body,
  } as unknown as Response;
}

/** A fetch mock that answers the /api/studio endpoints from memory. */
export function installFakeStudio(): FakeStudio {
  const studio: FakeStudio = {
    calls: [],
    catalog: structuredClone(CATALOG),
    projects: [],
    exports: [],
    previewReply: null,
    reply: null,
    previews: () => studio.calls.filter((call) => call.path === "/api/studio/preview").map((call) => call.body as PreviewRequest),
  };
  let previewCount = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : null;
    const path = url.pathname;
    const call = { method, path, body };
    studio.calls.push(call);
    const custom = await studio.reply?.(call);
    if (custom) return reply(custom.status, custom.body);

    if (path === "/api/studio/catalog") return reply(200, studio.catalog);
    if (path === "/api/studio/preview") {
      const custom = studio.previewReply?.(body);
      if (custom) return reply(custom.status, custom.body);
      previewCount += 1;
      return reply(200, { url: `/media/studio/previews/${previewCount}.png`, mode: body.mode, width: 640, height: 360, cached: false, ms: 5 });
    }
    if (path === "/api/studio/length") return reply(200, { length: null });
    if (path === "/api/studio/projects" && method === "GET") return reply(200, studio.projects);
    if (path === "/api/studio/projects" && method === "POST") {
      const project: Project = { id: `p${studio.projects.length + 1}`, created: 1, updated: 1, revision: 1, title: "", ...body };
      studio.projects.push(project);
      return reply(201, project);
    }
    const projectMatch = /^\/api\/studio\/projects\/([^/]+)$/.exec(path);
    if (projectMatch) {
      const project = studio.projects.find((item) => item.id === decodeURIComponent(projectMatch[1]));
      if (!project) return reply(404, { detail: "Project not found." });
      if (method === "PUT") {
        const { base_revision: base, ...fields } = body as { base_revision?: number };
        if (typeof base === "number" && (project.revision ?? 1) > base) {
          return reply(409, { detail: "This video was changed somewhere else. Read the project again before you edit it.", project });
        }
        Object.assign(project, fields, { updated: Number(project.updated) + 1, revision: (project.revision ?? 1) + 1 });
      }
      if (method === "DELETE") studio.projects.splice(studio.projects.indexOf(project), 1);
      return reply(200, project);
    }
    if (path === "/api/studio/exports" && method === "GET") return reply(200, studio.exports);
    if (path === "/api/studio/exports" && method === "POST") {
      const job: ExportJob = { id: `e${studio.exports.length + 1}`, status: "queued", progress: null, created: Date.now() / 1000, ...body };
      studio.exports.unshift(job);
      return reply(202, job);
    }
    const exportMatch = /^\/api\/studio\/exports\/([^/]+)$/.exec(path);
    if (exportMatch) {
      const job = studio.exports.find((item) => item.id === exportMatch[1]);
      if (!job) return reply(404, { detail: "Not found." });
      if (method === "DELETE") job.status = "cancelled";
      return reply(200, job);
    }
    if (path === "/api/studio/icons") return reply(200, ["clock", "gift", "star"]);
    if (path === "/api/files") return reply(200, { scripts: [], assets: [], media: [] });
    return reply(404, { detail: `No fake for ${method} ${path}` });
  });
  return studio;
}
