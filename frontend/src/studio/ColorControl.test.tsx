import { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { ColorControl } from "./ColorControl";
import { readRecentColors } from "./color";
import { CATALOG } from "./test/fixtures";

function Control() {
  const [value, setValue] = useState<string | null>(null);
  return <><span id="color-label">Accent color</span><ColorControl id="color" label="Accent color" value={value} onChange={setValue} theme={CATALOG.themes![0]} /><output data-testid="value">{String(value)}</output></>;
}

it("keeps the colour strip together and labels the custom swatch with its hex", async () => {
  const user = userEvent.setup();
  render(<Control />);
  const group = screen.getByRole("radiogroup", { name: "Accent color" });
  expect(within(group).getByRole("radio", { name: "Theme color" })).toHaveAttribute("aria-checked", "true");
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  await user.click(within(group).getByRole("radio", { name: "#2563EB" }));
  expect(screen.getByTestId("value")).toHaveTextContent("#2563EB");
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Pick any color" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Hex" }), { target: { value: "#ff3366" } });
  screen.getByRole("textbox", { name: "Hex" }).focus();
  await user.keyboard("{Enter}{Escape}");
  const custom = screen.getByRole("button", { name: "Custom color #FF3366" });
  expect(custom).toHaveAttribute("title", "Custom color #FF3366");
  expect(custom).toHaveStyle({ background: "#FF3366" });
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  await user.click(within(group).getByRole("radio", { name: "Theme color" }));
  expect(screen.getByTestId("value")).toHaveTextContent("null");
  expect(screen.getByRole("button", { name: "Pick any color" })).toBeInTheDocument();
});

it("remembers a custom color chosen in the popover", async () => {
  const user = userEvent.setup();
  render(<Control />);
  await user.click(screen.getByRole("button", { name: "Pick any color" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Hex" }), { target: { value: "1a2b3c" } });
  await user.keyboard("{Escape}");
  expect(readRecentColors()[0]).toBe("#1A2B3C");
  expect(screen.getByRole("button", { name: "Custom color #1A2B3C" })).toBeInTheDocument();
});

it("keeps the popover's hex validation message visible", async () => {
  const user = userEvent.setup();
  render(<Control />);
  await user.click(screen.getByRole("button", { name: "Pick any color" }));
  const hex = screen.getByRole("textbox", { name: "Hex" });
  fireEvent.change(hex, { target: { value: "12345" } });
  fireEvent.blur(hex);
  expect(hex).toHaveAttribute("aria-invalid", "true");
  expect(screen.getByRole("alert")).toHaveTextContent("Enter a 3 or 6 digit hex color");
  fireEvent.change(hex, { target: { value: "123456" } });
  expect(hex).toHaveAttribute("aria-invalid", "false");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  await user.keyboard("{Escape}");
});
