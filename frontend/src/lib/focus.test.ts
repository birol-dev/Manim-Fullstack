import { afterEach, describe, expect, it } from "vitest";

import { focusNextAfter } from "./focus";

const visible = () => true;

describe("focusNextAfter", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("moves focus to the next tabbable element outside the container", () => {
    document.body.innerHTML = `
      <button id="before">before</button>
      <div id="editor"><textarea id="inside"></textarea><button id="inner">in</button></div>
      <div role="separator" tabindex="0" id="handle"></div>
      <button id="skipped" tabindex="-1">no</button>
      <button id="disabled" disabled>no</button>
      <a id="next" href="#">next</a>`;
    const editor = document.getElementById("editor")!;
    document.getElementById("inside")!.focus();
    expect(focusNextAfter(editor, visible)).toBe(true);
    expect(document.activeElement?.id).toBe("next");
  });

  it("reports when nothing follows", () => {
    document.body.innerHTML = `<button>before</button><div id="editor"><textarea></textarea></div>`;
    expect(focusNextAfter(document.getElementById("editor")!, visible)).toBe(false);
  });
});
