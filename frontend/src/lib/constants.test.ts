import { beforeEach, describe, expect, it, vi } from "vitest";

type Constants = typeof import("./constants");

describe("server code-size limit", () => {
  let constants: Constants;

  beforeEach(async () => {
    vi.resetModules();
    constants = await import("./constants");
  });

  it("falls back to the 2 MB default before the server reports a limit", () => {
    expect(constants.getMaxCodeBytes()).toBe(constants.MAX_CODE_BYTES);
    expect(constants.MAX_CODE_BYTES).toBe(2 * 1024 * 1024);
  });

  it("uses max_code_bytes from /api/diagnostics", () => {
    constants.setMaxCodeBytes(5 * 1024 * 1024);
    expect(constants.getMaxCodeBytes()).toBe(5 * 1024 * 1024);
  });

  it.each([undefined, null, "4096", 0, -1, 1.5, Number.NaN])("ignores invalid value %p", (value) => {
    constants.setMaxCodeBytes(value);
    expect(constants.getMaxCodeBytes()).toBe(constants.MAX_CODE_BYTES);
  });

  it("formats the limit for messages", () => {
    expect(constants.formatByteLimit(2 * 1024 * 1024)).toBe("2 MB");
    expect(constants.formatByteLimit(1536 * 1024)).toBe("1.5 MB");
    expect(constants.formatByteLimit(512 * 1024)).toBe("512 KB");
    expect(constants.formatByteLimit(100)).toBe("100 bytes");
  });
});
