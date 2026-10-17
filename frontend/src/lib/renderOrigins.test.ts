import { beforeEach, describe, expect, it } from "vitest";

import { latestRenderFor, mediaScriptLabel, previewBelongsTo, previewFromMedia } from "./preview";
import { forgetRenderOrigin, recordRenderOrigin, renameRenderOrigins } from "./renderOrigins";
import { media } from "@/test/fakeServer";

const shared = media("MyScene", { path: "videos/my_scene/720p30/MyScene.mp4", script: "my_scene" });

beforeEach(() => localStorage.clear());

describe("render origins (browser and workspace files share the output folder by name)", () => {
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
