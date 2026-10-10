import { describe, expect, it } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";

import { useWorkspace } from "./useWorkspace";
import { loadBrowserFiles, STORAGE_KEYS, writeBrowserFile } from "@/lib/storage";
import { installFakeServer } from "@/test/fakeServer";

const stored = () => loadBrowserFiles();

describe("useWorkspace: a save right after a keystroke (R3 verify B)", () => {
  it("saves the keystroke, and the other tab then gets the conflict instead of silently overwriting it", async () => {
    installFakeServer();
    localStorage.setItem(STORAGE_KEYS.browserFiles, JSON.stringify({ "a.py": "# v1\n" }));
    const { result } = renderHook(() => useWorkspace({ mode: "browser", online: true }));
    await waitFor(() => expect(result.current.activeFile).toBe("a.py"));

    // Typing and Ctrl+S in the same task, before React commits the keystroke (a fast
    // typist, or automation): the save used to write the previous text, so the edit
    // never reached localStorage and the other tab overwrote it without a conflict.
    await act(async () => {
      result.current.setCode("# v1\n# tab one\n");
      await result.current.save();
    });
    expect(stored()["a.py"]).toBe("# v1\n# tab one\n");

    // The second tab, still based on "# v1", now has to ask.
    const other = renderHook(() => useWorkspace({ mode: "browser", online: true }));
    await waitFor(() => expect(other.result.current.activeFile).toBe("a.py"));
    writeBrowserFile("a.py", "# v1\n# tab one, again\n");
    let error: unknown = null;
    await act(async () => {
      other.result.current.setCode("# v1\n# tab two\n");
      await other.result.current.save().catch((err: unknown) => {
        error = err;
      });
    });
    expect(error).toMatchObject({ name: "SaveConflictError", reason: "changed" });
    expect(stored()["a.py"]).toBe("# v1\n# tab one, again\n");
  });
});
