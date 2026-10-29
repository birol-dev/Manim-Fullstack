import { useState } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ColorPickerButton } from "./ColorPicker";
import { hexToHsv, hsvToHex, parseHex, readRecentColors, RECENT_COLORS_KEY, rememberColor } from "./color";

beforeEach(() => localStorage.removeItem(RECENT_COLORS_KEY));
describe("hex parsing and recent colors", () => {
  it("normalizes shorthand and full hex, rejects incomplete or unsafe input", () => {
    for (const v of ["abc", "#AbC", " ABC "]) expect(parseHex(v)).toBe("#AABBCC");
    expect(parseHex("00aB91")).toBe("#00AB91");
    for (const v of ["", "#1234", "red", "#12345678", null, 123, "##fff"]) expect(parseHex(v)).toBeNull();
    for (const v of ["#000000", "#FFFFFF", "#FF0000", "#A31F99", "#12BC63"]) expect(hsvToHex(hexToHsv(v))).toBe(v);
  });
  it("keeps the last eight unique custom colors, newest first", () => {
    for (let n = 0; n < 10; n++) rememberColor(`#00000${n}`);
    rememberColor("#000005");
    expect(readRecentColors()).toEqual(["#000005", "#000009", "#000008", "#000007", "#000006", "#000004", "#000003", "#000002"]);
    localStorage.setItem(RECENT_COLORS_KEY, '["invalid", "#abc", "#AABBCC", false]');
    expect(readRecentColors()).toEqual(["#AABBCC"]);
    localStorage.setItem(RECENT_COLORS_KEY, "oops"); expect(readRecentColors()).toEqual([]);
  });
  it("works when storage is unavailable", () => {
    const read = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("denied"); });
    const write = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("denied"); });
    expect(readRecentColors()).toEqual([]); expect(rememberColor("abc")).toEqual(["#AABBCC"]);
    read.mockRestore(); write.mockRestore();
  });
});
function Picker() { const [value, setValue] = useState("#FF0000"); return <><ColorPickerButton aria-label="Choose color" value={value} onChange={setValue} swatches={["#FFFFFF"]} /><output>{value}</output></>; }
it("supports keyboard saturation, brightness, hue, hex, theme, and returns focus on Escape", async () => {
  const user = userEvent.setup(); render(<Picker />);
  const trigger = screen.getByRole("button", { name: "Choose color" });
  await user.click(trigger);
  const square = screen.getByRole("slider", { name: "Saturation and brightness" });
  expect(square).toHaveFocus();
  await user.keyboard("{Shift>}{ArrowLeft}{/Shift}{ArrowDown}");
  expect(square).toHaveAttribute("aria-valuenow", "90");
  expect(square.getAttribute("aria-valuetext")).toContain("brightness 99%");
  screen.getByRole("slider", { name: "Hue" }).focus(); await user.keyboard("{Shift>}{ArrowRight}{/Shift}");
  expect(screen.getByRole("slider", { name: "Hue" })).toHaveValue("10");
  fireEvent.change(screen.getByRole("textbox", { name: "Hex" }), { target: { value: "aBc" } });
  screen.getByRole("textbox", { name: "Hex" }).focus(); await user.keyboard("{Enter}");
  expect(screen.getByRole("status")).toHaveTextContent("#AABBCC");
  await user.keyboard("{Escape}"); expect(trigger).toHaveFocus(); expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(readRecentColors()).toEqual(["#AABBCC"]);
  await user.click(trigger); await user.click(screen.getByRole("button", { name: "Theme #FFFFFF" }));
  expect(screen.getByRole("status")).toHaveTextContent("#FFFFFF");
  await user.click(document.body); expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("opens table color cells with Enter and keeps picker arrows inside the popover", async () => {
  const { SchemaForm } = await import("./form/SchemaForm");
  const { fieldsOf } = await import("./schemaForm");
  const fields = fieldsOf({ properties: { rows: { type: "array", "x-widget": "table", items: { type: "object", properties: { color: { type: "string", "x-widget": "color", title: "Color" } } } } } });
  function Table() { const [values, setValues] = useState({ rows: [{ color: "#FF0000" }, { color: "#0000FF" }] }); return <SchemaForm fields={fields} values={values} onChange={(key, value) => setValues((v) => ({ ...v, [key]: value }))} />; }
  const user = userEvent.setup(); render(<Table />);
  const swatch = screen.getByRole("button", { name: "Color, row 1" });
  act(() => swatch.focus()); await user.keyboard("{Enter}");
  expect(screen.getByRole("dialog", { name: "Color picker" })).toBeInTheDocument();
  await user.keyboard("{ArrowDown}{Escape}");
  expect(swatch).toHaveFocus();
  expect(swatch).toHaveStyle({ background: "#FC0000" });
});

it("uses the optional eyedropper and normalizes its result", async () => {
  const open = vi.fn().mockResolvedValue({ sRGBHex: "#fFaa22" });
  vi.stubGlobal("EyeDropper", class { open = open; });
  try {
    const user = userEvent.setup();
    render(<Picker />);
    await user.click(screen.getByRole("button", { name: "Choose color" }));
    await user.click(screen.getByRole("button", { name: "Pick color from screen" }));
    expect(open).toHaveBeenCalledOnce();
    expect(screen.getByRole("status")).toHaveTextContent("#FFAA22");
    await user.keyboard("{Escape}");
    expect(readRecentColors()).toEqual(["#FFAA22"]);
  } finally { vi.unstubAllGlobals(); }
});

it("ignores an eyedropper result that arrives after the picker closes", async () => {
  let finish!: (result: { sRGBHex: string }) => void;
  const open = vi.fn(() => new Promise<{ sRGBHex: string }>((resolve) => { finish = resolve; }));
  vi.stubGlobal("EyeDropper", class { open = open; });
  try {
    const user = userEvent.setup();
    render(<Picker />);
    await user.click(screen.getByRole("button", { name: "Choose color" }));
    await user.click(screen.getByRole("button", { name: "Pick color from screen" }));
    await user.keyboard("{Escape}");
    await act(async () => finish({ sRGBHex: "#abcdef" }));
    expect(screen.getByRole("status")).toHaveTextContent("#FF0000");
    expect(readRecentColors()).toEqual([]);
  } finally { vi.unstubAllGlobals(); }
});
