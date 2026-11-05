import { expect, it } from "vitest";

import { designFields, replaceDesignField } from "./designFields";

it("edits marked strings and colors in place while preserving the Python around them", () => {
  const source = 'TITLE = "A \\"B\\" title"  # studio: Headline\r\nACCENT = "#8BE2B4"  # studio: Accent\r\nOTHER = "untouched"\r\n';
  const [title, color] = designFields(source);
  expect(title).toMatchObject({ label: "Headline", value: 'A "B" title', type: "text" });
  expect(color).toMatchObject({ label: "Accent", value: "#8BE2B4", type: "color" });
  const edited = replaceDesignField(source, title, 'New "title"');
  expect(edited).toBe('TITLE = "New \\"title\\""  # studio: Headline\r\nACCENT = "#8BE2B4"  # studio: Accent\r\nOTHER = "untouched"\r\n');
  expect(designFields(edited)).toHaveLength(2);
});
