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

describe("make many routes", () => {
  it("parses a template card and a saved project", () => {
    expect(parseRoute("#/many/announcement/weekend-sale"))
      .toEqual({ kind: "many", template: "announcement", preset: "weekend-sale" });
    expect(parseRoute("#/many/announcement")).toEqual({ kind: "many", template: "announcement", preset: "" });
    expect(parseRoute("#/many/project/0123456789abcdef"))
      .toEqual({ kind: "many-project", id: "0123456789abcdef" });
    expect(parseRoute("#/many/project")).toEqual({ kind: "gallery" });
    expect(parseRoute("#/many/a%2Fb/c%20d")).toEqual({ kind: "many", template: "a/b", preset: "c d" });
  });

  it("builds the same hashes", () => {
    const routes: Route[] = [
      { kind: "many", template: "announcement", preset: "weekend-sale" },
      { kind: "many", template: "a/b", preset: "c d" },
      { kind: "many-project", id: "0123456789abcdef" },
    ];
    for (const route of routes) expect(parseRoute(routeHash(route))).toEqual(route);
    expect(routeHash({ kind: "many", template: "countdown", preset: "" })).toBe("#/many/countdown");
    expect(routeHash({ kind: "many-project", id: "abc" })).toBe("#/many/project/abc");
  });
});
