import { describe, expect, it } from "vitest";

import { parseRoute, routeHash, type Route } from "./router";

describe("settings and welcome routes", () => {
  it("parses a settings section and the welcome tour", () => {
    expect(parseRoute("#/settings")).toEqual({ kind: "settings" });
    expect(parseRoute("#/settings/ai")).toEqual({ kind: "settings", section: "ai" });
    expect(parseRoute("#/settings/appearance")).toEqual({ kind: "settings", section: "appearance" });
    expect(parseRoute("#/settings/a%2Fb")).toEqual({ kind: "settings", section: "a/b" });
    expect(parseRoute("#/welcome")).toEqual({ kind: "welcome" });
  });

  it("builds their hashes and survives a round trip", () => {
    const routes: Route[] = [
      { kind: "settings" },
      { kind: "settings", section: "ai" },
      { kind: "settings", section: "a/b" },
      { kind: "welcome" },
    ];
    for (const route of routes) expect(parseRoute(routeHash(route))).toEqual(route);
    expect(routeHash({ kind: "settings" })).toBe("#/settings");
    expect(routeHash({ kind: "settings", section: "ai" })).toBe("#/settings/ai");
    expect(routeHash({ kind: "welcome" })).toBe("#/welcome");
  });
});
