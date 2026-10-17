import { beforeEach, describe, expect, it } from "vitest";

import { latestRenderFor, mediaScriptLabel, mediaStorage, previewBelongsTo, previewFromMedia } from "./preview";
import { forgetRenderOrigin, recordRenderOrigin, renameRenderOrigins } from "./renderOrigins";
import { media } from "@/test/fakeServer";

const shared = media("MyScene", { path: "videos/my_scene/720p30/MyScene.mp4", script: "my_scene" });

beforeEach(() => localStorage.clear());

describe("render origins (older servers shared one output folder per name)", () => {
  it("counts an unrecorded output as the workspace folder's", () => {
    expect(latestRenderFor([shared], "my_scene.py", "MyScene", "disk")).toBe(shared);
    expect(latestRenderFor([shared], "my_scene.py", "MyScene", "browser")).toBeNull();
  });

  it("gives an output to the storage mode that last rendered it", () => {
    recordRenderOrigin(shared.path, "browser", "my_scene.py");
    expect(latestRenderFor([shared], "my_scene.py", "MyScene", "browser")).toBe(shared);
    expect(latestRenderFor([shared], "my_scene.py", "MyScene", "disk")).toBeNull();
    const item = previewFromMedia(shared);
    expect(item.storage).toBe("browser");
    expect(previewBelongsTo(item, "my_scene.py", "MyScene", "browser")).toBe(true);
    expect(previewBelongsTo(item, "my_scene.py", "MyScene", "disk")).toBe(false);
    forgetRenderOrigin(shared.path);
    expect(previewFromMedia(shared).storage).toBe("disk");
  });

  it("labels and finds an output by the script's current name after a rename", () => {
    const item = media("Intro");
    recordRenderOrigin(item.path, "disk", "renamed.py");
    expect(mediaScriptLabel(item)).toBe("renamed.py");
    expect(latestRenderFor([item], "renamed.py", "Intro", "disk")).toBe(item);
    expect(latestRenderFor([item], "example.py", "Intro", "disk")).toBeNull();
    renameRenderOrigins("disk", "renamed.py", "final.py");
    expect(mediaScriptLabel(item)).toBe("final.py");
    expect(mediaScriptLabel(media("Outro"))).toBe("example.py");
  });
});

describe("render origins reported by the server (browser renders have their own folder)", () => {
  const disk = media("MyScene", { path: "videos/my_scene/720p30/MyScene.mp4", script: "my_scene", storage: "disk" });
  const browser = media("MyScene", {
    path: "videos/.browser/my_scene/720p30/MyScene.mp4",
    script: "my_scene",
    storage: "browser",
    modified: disk.modified - 10,
  });

  it("keeps each file's render apart, whichever is newer", () => {
    expect(latestRenderFor([disk, browser], "my_scene.py", "MyScene", "disk")).toBe(disk);
    expect(latestRenderFor([disk, browser], "my_scene.py", "MyScene", "browser")).toBe(browser);
    expect(previewFromMedia(browser).storage).toBe("browser");
    expect(mediaStorage(browser)).toBe("browser");
    expect(mediaStorage(disk)).toBe("disk");
  });

  it("still labels a browser render with the name it was renamed to", () => {
    recordRenderOrigin(browser.path, "browser", "renamed.py");
    expect(mediaScriptLabel(browser)).toBe("renamed.py");
    // A stray disk record can't move an output out of the browser folder.
    recordRenderOrigin(browser.path, "disk", "other.py");
    expect(mediaStorage(browser)).toBe("browser");
    expect(mediaScriptLabel(browser)).toBe("my_scene.py");
  });
});
