import { describe, expect, it } from "vitest";

import { media } from "@/test/fakeServer";
import { latestRenderFor, previewBelongsTo, previewFromMedia, scriptStem } from "./preview";

describe("preview binding", () => {
  const old = media("Intro", { modified: 100, path: "videos/example/480p15/Intro.mp4", quality: "480p15" });
  const fresh = media("Intro", { modified: 200 });
  const outro = media("Outro", { modified: 300 });
  const other = media("Intro", { modified: 400, script: "notes", path: "videos/notes/720p30/Intro.mp4" });

  it("finds a file's newest render of a scene", () => {
    expect(scriptStem("example.py")).toBe("example");
    expect(latestRenderFor([old, fresh, outro, other], "example.py", "Intro")).toBe(fresh);
    expect(latestRenderFor([old, fresh, outro, other], "example.py", "")).toBe(outro);
    expect(latestRenderFor([old, fresh, other], "example.py", "Missing")).toBeNull();
    expect(latestRenderFor([other], "example.py", "Intro")).toBeNull();
  });

  it("records which file and scene a preview belongs to", () => {
    const item = previewFromMedia(fresh);
    expect(item).toMatchObject({ file: "example.py", scene: "Intro", mediaPath: fresh.path, title: "Intro" });
    expect(previewBelongsTo(item, "example.py", "Intro")).toBe(true);
    expect(previewBelongsTo(item, "example.py", "Outro")).toBe(false);
    expect(previewBelongsTo(item, "notes.py", "Intro")).toBe(false);
    expect(previewBelongsTo(null, "example.py", "Intro")).toBe(false);
  });
});
