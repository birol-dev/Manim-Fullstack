import { describe, it, expect } from "vitest";
import { cn } from "./utils";

describe("cn utility", () => {
  it("merges class names cleanly", () => {
    expect(cn("px-2 py-1", "bg-red-500")).toBe("px-2 py-1 bg-red-500");
  });

  it("handles conditional class names and falsy values", () => {
    const isHidden = false;
    expect(cn("base", isHidden && "hidden", null, undefined, "extra")).toBe("base extra");
  });

  it("resolves conflicting tailwind classes with twMerge", () => {
    expect(cn("px-2 py-1", "px-4")).toBe("py-1 px-4");
  });
});
