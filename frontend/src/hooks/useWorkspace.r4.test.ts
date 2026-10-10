// Fix round 4: parse rejections, per-file browser storage (stale tabs, migration),
// no stale scenes on a browser file switch, and browser-storage file name rules.
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { toast } from "sonner";

import { useWorkspace } from "./useWorkspace";
import { MAX_CODE_BYTES, setMaxCodeBytes } from "@/lib/constants";
import { BROWSER_STARTER_NAME, browserFileKey, loadBrowserFiles, readBrowserFile, STORAGE_KEYS, writeBrowserFile } from "@/lib/storage";
import { installFakeServer } from "@/test/fakeServer";

afterEach(() => setMaxCodeBytes(MAX_CODE_BYTES));

const A = "from manim import *\n\nclass Alpha(Scene):\n    def construct(self):\n        self.wait()\n";
const B = "from manim import *\n\nclass Beta(Scene):\n    def construct(self):\n        self.wait()\n";

function browserHook() {
  return renderHook(() => useWorkspace({ mode: "browser", online: true }));
}

describe("R4 #6: a too-large buffer while typing", () => {
  it("toasts the size limit and clears the scene list instead of an unhandled rejection", async () => {
    installFakeServer();
    const rejections: unknown[] = [];
    const onRejection = (reason: unknown) => rejections.push(reason);
    process.on("unhandledRejection", onRejection);
    const error = vi.spyOn(toast, "error");
    try {
      const { result } = renderHook(() => useWorkspace({ mode: "disk", online: true }));
      await waitFor(() => expect(result.current.activeFile).not.toBeNull());
      await waitFor(() => expect(result.current.scenes.length).toBeGreaterThan(0));
      const scene = result.current.selectedScene;
      setMaxCodeBytes(200);
      act(() => result.current.setCode(`${result.current.code}\n${"x = 1\n".repeat(100)}`));
      await waitFor(() => expect(error).toHaveBeenCalledWith(expect.stringMatching(/larger than/), { id: "code-size" }));
      // The old scene list and timeline described other code: gone. The picked scene stays.
      // (Waited for: the toast is recorded before React commits the cleared state.)
      await waitFor(() => expect(result.current.scenes).toEqual([]));
      expect(result.current.animations).toEqual({});
      expect(result.current.selectedScene).toBe(scene);
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(rejections).toEqual([]);
      // parseNow rejects too (a promise, not a synchronous throw).
      let caught: unknown = null;
      await act(async () => {
        await result.current.parseNow().catch((err: unknown) => (caught = err));
      });
      expect(caught).toMatchObject({ status: 413 });
    } finally {
      process.off("unhandledRejection", onRejection);
    }
  });
});

describe("R4 #8: browser storage writes one key per file", () => {
  it("a tab with a stale view of storage can't undo another tab's save of a different file", async () => {
    installFakeServer();
    writeBrowserFile("a.py", "# a v1\n");
    writeBrowserFile("b.py", "# b v1\n");
    const { result } = browserHook();
    await waitFor(() => expect(result.current.activeFile).toBe("a.py"));

    // What this tab's storage looked like before the other tab saved b.py ...
    const snapshot = new Map(Object.keys(localStorage).map((key) => [key, localStorage.getItem(key)]));
    writeBrowserFile("b.py", "# b v2 from the other tab\n");
    // ... and it still reads that (Chrome's per-process localStorage cache can lag).
    const realGet = Storage.prototype.getItem;
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (this: Storage, key: string) {
      return snapshot.has(key) ? (snapshot.get(key) ?? null) : realGet.call(this, key);
    });
    await act(async () => {
      result.current.setCode("# a v2\n");
      await result.current.save();
    });
    vi.restoreAllMocks();

    expect(readBrowserFile("a.py")).toBe("# a v2\n");
    expect(readBrowserFile("b.py")).toBe("# b v2 from the other tab\n");
    expect(localStorage.getItem(STORAGE_KEYS.browserFiles)).toBeNull();
  });

  it("migrates the old one-map format once, without overwriting files already stored per key", () => {
    localStorage.setItem(STORAGE_KEYS.browserFiles, JSON.stringify({ "old.py": "# old\n", "both.py": "# from the map\n" }));
    localStorage.setItem(browserFileKey("both.py"), "# per key wins\n");
    expect(loadBrowserFiles()).toEqual({ "old.py": "# old\n", "both.py": "# per key wins\n" });
    expect(localStorage.getItem(STORAGE_KEYS.browserFiles)).toBeNull();
    expect(localStorage.getItem(browserFileKey("old.py"))).toBe("# old\n");
  });
});

describe("R4 #9: switching browser files never shows the previous file's scenes", () => {
  it("has the new file's scenes in the same render that shows the new file", async () => {
    installFakeServer();
    writeBrowserFile("a.py", A);
    writeBrowserFile("b.py", B);
    const seen: Array<[string | null, string[], string]> = [];
    const { result } = renderHook(() => {
      const workspace = useWorkspace({ mode: "browser", online: true });
      seen.push([workspace.activeFile, workspace.scenes, workspace.selectedScene]);
      return workspace;
    });
    await waitFor(() => expect(result.current.scenes).toEqual(["Alpha"]));
    await act(async () => {
      await result.current.openFile("b.py");
    });
    expect(result.current.scenes).toEqual(["Beta"]);
    const stale = seen.filter(([file, scenes, scene]) => file === "b.py" && (scenes.includes("Alpha") || scene === "Alpha"));
    expect(stale).toEqual([]);
  });

  it("drops the scenes of a deleted file when no file is left open", async () => {
    installFakeServer();
    localStorage.setItem("mc.browserSeeded", "true");
    writeBrowserFile("a.py", A);
    const { result } = browserHook();
    await waitFor(() => expect(result.current.scenes).toEqual(["Alpha"]));
    await act(async () => {
      await result.current.deleteFile("a.py");
    });
    expect(result.current.activeFile).toBeNull();
    expect(result.current.scenes).toEqual([]);
    expect(result.current.selectedScene).toBe("");
    expect(result.current.animations).toEqual({});
  });

  it("never pairs the scenes of one storage mode's file with the other mode while switching", async () => {
    installFakeServer({ scripts: { "other.py": "from manim import *\n\nclass Other(Scene):\n    pass\n" } });
    writeBrowserFile("a.py", A);
    const seen: Array<[string, string[], string]> = [];
    const { result, rerender } = renderHook(
      ({ mode }: { mode: "browser" | "disk" }) => {
        const workspace = useWorkspace({ mode, online: true });
        seen.push([mode, workspace.scenes, workspace.selectedScene]);
        return workspace;
      },
      { initialProps: { mode: "browser" as "browser" | "disk" } },
    );
    await waitFor(() => expect(result.current.scenes).toEqual(["Alpha"]));
    rerender({ mode: "disk" });
    await waitFor(() => expect(result.current.scenes).toEqual(["Other"]));
    expect(seen.filter(([mode, scenes, scene]) => mode === "disk" && (scenes.includes("Alpha") || scene === "Alpha"))).toEqual([]);
  });

  it("keeps the scenes when the open file is renamed", async () => {
    installFakeServer();
    writeBrowserFile("a.py", A);
    const { result } = browserHook();
    await waitFor(() => expect(result.current.scenes).toEqual(["Alpha"]));
    await act(async () => {
      await result.current.renameFile("a.py", "renamed.py");
    });
    expect(result.current.activeFile).toBe("renamed.py");
    expect(result.current.scenes).toEqual(["Alpha"]);
    expect(result.current.selectedScene).toBe("Alpha");
  });
});

describe("R4 browser storage: rename, name clashes, and the starter script", () => {
  it("(a) renaming a script another tab deleted keeps the text and reports it missing, without an empty file", async () => {
    installFakeServer();
    writeBrowserFile("a.py", "# a\n");
    writeBrowserFile("z.py", "# z\n");
    const { result } = browserHook();
    await waitFor(() => expect(result.current.activeFile).toBe("a.py"));
    act(() => result.current.setCode("# a, edited here\n"));
    localStorage.removeItem(browserFileKey("a.py")); // the other tab deleted it

    let error: unknown = null;
    await act(async () => {
      await result.current.renameFile("a.py", "renamed.py").catch((err: unknown) => (error = err));
    });
    expect(error).toMatchObject({ name: "SaveConflictError", reason: "missing", filename: "a.py" });
    expect(readBrowserFile("renamed.py")).toBeUndefined();
    expect(result.current.activeFile).toBe("a.py");
    expect(result.current.code).toBe("# a, edited here\n");
    expect(result.current.isDirty).toBe(true);

    // A script that isn't open: a plain error, and nothing created either.
    localStorage.removeItem(browserFileKey("z.py"));
    let other: unknown = null;
    await act(async () => {
      await result.current.renameFile("z.py", "zz.py").catch((err: unknown) => (other = err));
    });
    expect(String(other)).toMatch(/no longer exists/);
    expect(readBrowserFile("zz.py")).toBeUndefined();
  });

  it("(b) refuses names that differ only by case (NFC + case fold), on create and rename", async () => {
    installFakeServer();
    writeBrowserFile("caf\u00e9.py", "# nfc\n");
    writeBrowserFile("b.py", "# b\n");
    const { result } = browserHook();
    await waitFor(() => expect(result.current.activeFile).not.toBeNull());

    const failure = async (run: () => Promise<unknown>) => {
      let error: unknown = null;
      await act(async () => {
        await run().catch((err: unknown) => (error = err));
      });
      return String(error);
    };
    expect(await failure(() => result.current.createFile("CAF\u00c9.py", "# x\n"))).toMatch(/'caf\u00e9\.py' already exists\. File names that differ only by case/);
    expect(await failure(() => result.current.createFile("B.py", "# x\n"))).toMatch(/'b\.py' already exists/);
    expect(await failure(() => result.current.createFile("b.py", "# x\n"))).toMatch(/b\.py already exists/);
    expect(await failure(() => result.current.renameFile("b.py", "Caf\u00e9.py"))).toMatch(/differ only by case/);
    expect(Object.keys(loadBrowserFiles()).sort()).toEqual(["b.py", "caf\u00e9.py"]);
    // A case-only rename of the file itself is fine.
    await act(async () => {
      await result.current.renameFile("b.py", "B.py");
    });
    expect(Object.keys(loadBrowserFiles()).sort()).toEqual(["B.py", "caf\u00e9.py"]);
  });

  it("(c) seeds the starter script once; deleting the last script leaves an empty list, also after a reload", async () => {
    installFakeServer();
    const first = browserHook();
    await waitFor(() => expect(first.result.current.activeFile).toBe(BROWSER_STARTER_NAME));
    await act(async () => {
      await first.result.current.deleteFile(BROWSER_STARTER_NAME);
    });
    expect(first.result.current.files.scripts).toEqual([]);
    expect(first.result.current.activeFile).toBeNull();
    first.unmount();

    const reloaded = browserHook();
    await waitFor(() => expect(reloaded.result.current.filesStatus).toBe("ready"));
    expect(reloaded.result.current.files.scripts).toEqual([]);
    expect(reloaded.result.current.activeFile).toBeNull();
    expect(loadBrowserFiles()).toEqual({});
  });
});

describe("R4 #6: back under the limit", () => {
  it("parses again when the edit is undone to the code that was parsed before", async () => {
    installFakeServer();
    const { result } = renderHook(() => useWorkspace({ mode: "disk", online: true }));
    await waitFor(() => expect(result.current.scenes.length).toBeGreaterThan(0));
    const before = result.current.scenes;
    const original = result.current.code;
    vi.spyOn(toast, "error");
    setMaxCodeBytes(200);
    act(() => result.current.setCode(`${original}\n${"x = 1\n".repeat(100)}`));
    await waitFor(() => expect(result.current.scenes).toEqual([]));
    setMaxCodeBytes(MAX_CODE_BYTES);
    act(() => result.current.setCode(original));
    await waitFor(() => expect(result.current.scenes).toEqual(before));
  });
});
