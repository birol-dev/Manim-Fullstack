import { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { ColorControl } from "./ColorControl";
import { CATALOG } from "./test/fixtures";

function Control() {
  const [value, setValue] = useState<string | null>(null);
  return <><span id="color-label">Accent color</span><ColorControl id="color" label="Accent color" value={value} onChange={setValue} theme={CATALOG.themes![0]} /><output data-testid="value">{String(value)}</output></>;
}

it("keeps the colour strip together and shows a hex field only for a custom colour", async () => {
  const user = userEvent.setup();
  render(<Control />);
  const group = screen.getByRole("radiogroup", { name: "Accent color" });
  expect(within(group).getByRole("radio", { name: "Theme color" })).toHaveAttribute("aria-checked", "true");
  expect(screen.queryByRole("textbox", { name: "Accent color, color code" })).not.toBeInTheDocument();
  await user.click(within(group).getByRole("radio", { name: "#2563EB" }));
  expect(screen.getByTestId("value")).toHaveTextContent("#2563EB");
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Pick any color" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Hex" }), { target: { value: "#ff3366" } });
  screen.getByRole("textbox", { name: "Hex" }).focus();
  await user.keyboard("{Enter}{Escape}");
  const code = screen.getByRole("textbox", { name: "Accent color, color code" });
  expect(code).toHaveValue("#FF3366");
  expect(code).toHaveAttribute("placeholder", "#FF3366");
  expect(code).not.toHaveClass("uppercase", "font-mono");
  fireEvent.change(code, { target: { value: "123456" } });
  expect(screen.getByTestId("value")).toHaveTextContent("#123456");
  await user.click(within(group).getByRole("radio", { name: "Theme color" }));
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(screen.getByTestId("value")).toHaveTextContent("null");
});
