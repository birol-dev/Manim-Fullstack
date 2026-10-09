// Fix round 3: test headroom so the App-level tests don't time out under load.
import { getConfig } from "@testing-library/react";
import { describe, expect, it } from "vitest";

describe("test timeouts", () => {
  it("gives findBy*/waitFor 5 s", () => {
    expect(getConfig().asyncUtilTimeout).toBe(5_000);
  });

  it("gives each test 15 s", async () => {
    const { default: config } = await import("../../vite.config");
    const test = (config as { test?: { testTimeout?: number; hookTimeout?: number } }).test;
    expect(test?.testTimeout).toBe(15_000);
    expect(test?.hookTimeout).toBe(15_000);
  });
});
