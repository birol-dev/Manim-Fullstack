import { describe, expect, it } from "vitest";

import { filterCards } from "./options";
import type { Card, TemplateInfo } from "./types";

const card = (id: string, overrides: Partial<Card> = {}): Card => ({
  id,
  template: "announce",
  title: id,
  summary: "",
  category: "announce",
  params: {},
  settings: {},
  tags: [],
  ...overrides,
});

const template = (id: string, overrides: Partial<TemplateInfo> = {}): TemplateInfo => ({
  id,
  version: 1,
  title: "Announcement",
  summary: "",
  category: "announce",
  aspects: ["16:9"],
  default_aspect: "16:9",
  min_length: 3,
  max_length: 10,
  default_length: 5,
  loopable: false,
  length_from_params: false,
  tags: [],
  schema: {},
  defaults: {},
  presets: [],
  ...overrides,
});

const templates = new Map([
  ["announce", template("announce", { tags: ["sale"] })],
  ["quiet", template("quiet", { title: "Quiet notice" })],
]);

describe("filterCards", () => {
  it("ranks title, card tags, summary, then template matches", () => {
    const cards = [
      card("via-template", { title: "We're hiring", summary: "Join the team.", tags: ["jobs"] }),
      card("via-summary", { title: "Holiday hours", summary: "Our sale week hours.", tags: ["hours"] }),
      card("via-tag", { title: "Big news", summary: "A short note.", tags: ["sale"] }),
      card("via-title", { title: "Weekend sale", summary: "Everything must go.", tags: ["shop"] }),
      card("no-match", { title: "Office move", template: "quiet" }),
    ];

    expect(filterCards(cards, "sale", templates).map((item) => item.id)).toEqual([
      "via-title",
      "via-tag",
      "via-summary",
      "via-template",
    ]);
  });

  it("keeps catalogue order within each tier", () => {
    const cards = [
      card("first", { title: "Holiday sale" }),
      card("second", { title: "Big news", tags: ["sale"] }),
      card("third", { title: "Weekend sale" }),
      card("fourth", { title: "Short notice", summary: "A sale starts now." }),
    ];

    expect(filterCards(cards, "sale", templates).map((item) => item.id)).toEqual([
      "first",
      "third",
      "second",
      "fourth",
    ]);
  });

  it("needs every word in the same tier and still finds split card and template matches", () => {
    const cards = [
      card("titled", { title: "Weekend sale" }),
      card("tagged", { title: "Weekend", tags: ["sale"] }),
      card("summarized", { title: "Weekend", summary: "Our sale" }),
      card("template-only", { title: "Weekend", tags: ["deals"] }),
      card("partial", { title: "Weekend", template: "quiet" }),
    ];

    expect(filterCards(cards, "WEEKEND sale", templates).map((item) => item.id)).toEqual([
      "titled",
      "tagged",
      "summarized",
      "template-only",
    ]);
  });

  it("returns every card in place for an empty query", () => {
    const cards = [card("one"), card("two")];

    expect(filterCards(cards, "   ", templates)).toBe(cards);
  });
});
