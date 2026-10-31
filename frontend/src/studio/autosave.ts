/**
 * Autosave for the editor: the first edit creates the project, later edits update it, both
 * debounced. One save runs at a time; edits made meanwhile are saved right after.
 */
import type { Params, Project, RenderSettings } from "./types";

export interface Snapshot {
  title: string;
  template: string;
  params: Params;
  settings: Partial<RenderSettings>;
}

export type SaveStatus = "idle" | "pending" | "saving" | "saved" | "error";

interface AutosaverOptions {
  projectId: string | null;
  create: (snapshot: Snapshot, keepalive: boolean) => Promise<Project>;
  update: (id: string, snapshot: Snapshot, keepalive: boolean) => Promise<unknown>;
  onStatus: (status: SaveStatus, error?: unknown) => void;
  onCreated: (project: Project) => void;
  /** Answer true when the save was refused because the project changed elsewhere: saving stops. */
  onConflict?: (error: unknown) => boolean;
  delay?: number;
}

export class Autosaver {
  private projectId: string | null;
  private readonly options: AutosaverOptions;
  private readonly delay: number;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private latest: Snapshot | null = null;
  private changed = 0;
  private saved = 0;
  private saving: Promise<void> | null = null;
  private disposed = false;
  private stopped = false;
  private keepalive = false;

  constructor(options: AutosaverOptions) {
    this.options = options;
    this.projectId = options.projectId;
    this.delay = options.delay ?? 800;
  }

  get id() {
    return this.projectId;
  }

  get dirty() {
    return this.changed > this.saved;
  }

  change(snapshot: Snapshot) {
    if (this.disposed || this.stopped) return;
    this.latest = snapshot;
    this.changed += 1;
    this.options.onStatus("pending");
    this.arm();
  }

  /** Save now (leaving the editor). With keepalive the request outlives the page. */
  flush(keepalive = false) {
    if (this.disposed || this.stopped) return;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    if (!this.dirty || !this.latest) return;
    this.keepalive ||= keepalive;
    void this.save();
  }

  /** Stop saving for good: a save was refused because the project changed elsewhere. */
  stop() {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }

  /** Save again from a fresh copy, after the person loaded the newest version. */
  resume() {
    if (this.disposed) return;
    this.stopped = false;
    this.latest = null;
    this.changed = 0;
    this.saved = 0;
    this.keepalive = false;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }

  dispose() {
    this.disposed = true;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }

  private arm() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.save();
    }, this.delay);
  }

  private async save(): Promise<void> {
    if (this.stopped) return;
    if (this.saving) return this.saving;
    const snapshot = this.latest;
    if (!snapshot || !this.dirty) return;
    const version = this.changed;
    const keepalive = this.keepalive;
    this.keepalive = false;
    const report = (status: SaveStatus, error?: unknown) => {
      if (!this.disposed) this.options.onStatus(status, error);
    };
    report("saving");
    this.saving = (async () => {
      let ok = false;
      try {
        if (this.projectId) {
          await this.options.update(this.projectId, snapshot, keepalive);
        } else {
          const project = await this.options.create(snapshot, keepalive);
          this.projectId = project.id;
          if (!this.disposed) this.options.onCreated(project);
        }
        ok = true;
        this.saved = Math.max(this.saved, version);
        report(this.dirty ? "pending" : "saved");
      } catch (error) {
        if (!this.disposed && this.options.onConflict?.(error)) {
          // The project changed elsewhere: never retry or overwrite it.
          this.stop();
          report("idle");
          return;
        }
        // No automatic retry (a refused save would loop); the next edit tries again.
        report("error", error);
      } finally {
        this.saving = null;
      }
      // Edits made while this save ran: save them too (an unmounted editor still gets them saved).
      if (ok && this.dirty && !this.timer && !this.stopped) {
        if (this.disposed || this.keepalive) void this.save();
        else this.arm();
      }
    })();
    return this.saving;
  }
}
