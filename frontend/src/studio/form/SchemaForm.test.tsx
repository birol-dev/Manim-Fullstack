import { useState } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { fieldsOf } from "../schemaForm";
import type { JsonSchema, Params } from "../types";
import { SchemaForm } from "./SchemaForm";

const schema: JsonSchema = { properties: {
  answers: { type: "array", title: "Answers", "x-item-title": "Answer", minItems: 2, maxItems: 4, items: { type: "object", properties: { text: { type: "string", title: "Answer", default: "" } } } },
  correct: { type: "integer", title: "Correct answer", minimum: 1, maximum: 4, "x-choice-of": "answers", description: "The position of the correct answer in the list." },
} };

function Form() {
  const [values, setValues] = useState<Params>({ answers: [{ text: "Venus" }, { text: "Mars" }, { text: "Jupiter" }, { text: "Mercury" }], correct: 2 });
  return <>
    <SchemaForm fields={fieldsOf(schema)} values={values} onChange={(key, value, related) => setValues((previous) => ({ ...previous, ...related, [key]: value }))} />
    <output data-testid="values">{JSON.stringify(values)}</output>
  </>;
}

it("renders live sibling choices and preserves the selected answer through rename, move and removal", async () => {
  const user = userEvent.setup();
  render(<Form />);
  const group = screen.getByRole("radiogroup", { name: "Correct answer" });
  expect(within(group).getByRole("radio", { name: "B Mars" })).toBeChecked();
  expect(screen.queryByText("The position of the correct answer in the list.")).not.toBeInTheDocument();
  expect(screen.queryByRole("textbox", { name: "Correct answer" })).not.toBeInTheDocument();
  await user.clear(screen.getByRole("textbox", { name: "Answer 2" }));
  await user.type(screen.getByRole("textbox", { name: "Answer 2" }), "Red planet");
  expect(within(group).getByRole("radio", { name: "B Red planet" })).toBeChecked();
  await user.click(within(group).getByRole("radio", { name: "D Mercury" }));
  await user.click(screen.getByRole("button", { name: "Move Answer 4 up" }));
  expect(within(group).getByRole("radio", { name: "C Mercury" })).toBeChecked();
  expect(JSON.parse(screen.getByTestId("values").textContent!).correct).toBe(3);
  await user.click(screen.getByRole("button", { name: "Remove Answer 1" }));
  expect(within(group).getByRole("radio", { name: "B Mercury" })).toBeChecked();
  await user.click(screen.getByRole("button", { name: "Remove Answer 2" }));
  expect(within(group).getByRole("radio", { name: "B Jupiter" })).toBeChecked();
  expect(JSON.parse(screen.getByTestId("values").textContent!).correct).toBe(2);
});

it("offers newly added empty answers by name and supports keyboard selection", async () => {
  const user = userEvent.setup();
  render(<Form />);
  await user.click(screen.getByRole("button", { name: "Remove Answer 4" }));
  await user.click(screen.getByRole("button", { name: "Add answer" }));
  const group = screen.getByRole("radiogroup", { name: "Correct answer" });
  await user.click(within(group).getByRole("radio", { name: "D Answer 4" }));
  expect(JSON.parse(screen.getByTestId("values").textContent!).correct).toBe(4);
  await user.keyboard("{ArrowLeft}");
  expect(within(group).getByRole("radio", { name: "C Jupiter" })).toBeChecked();
  await user.click(screen.getByRole("button", { name: "Move Answer 2 down" }));
  expect(within(group).getByRole("radio", { name: "B Jupiter" })).toBeChecked();
});

it("uses short UI help for text, duration and toggles, keeping legacy descriptions as a fallback", () => {
  const fields = fieldsOf({ properties: {
    greeting: { type: "string", title: "Greeting", description: "Wrap *words* in asterisks. Full agent description.", "x-help": "Your greeting." },
    seconds: { type: "number", title: "Timer length", "x-widget": "duration", description: "Time in seconds (5 minutes = 300).", "x-help": "How long the timer runs." },
    enabled: { type: "boolean", title: "Enabled", description: "Detailed toggle information.", "x-help": "Show the detail." },
    note: { type: "string", title: "Note", description: "Legacy help." },
  } });
  render(<SchemaForm fields={fields} values={{ greeting: "Hi", seconds: 300, enabled: true, note: "" }} onChange={() => {}} />);
  expect(screen.getByRole("textbox", { name: "Greeting" })).toHaveAccessibleDescription("Your greeting. Tip: *best* → best");
  expect(screen.getByRole("textbox", { name: "Timer length" })).toHaveAccessibleDescription("How long the timer runs.");
  expect(screen.getByRole("switch", { name: "Enabled" })).toHaveAccessibleDescription("Show the detail.");
  expect(screen.getByRole("textbox", { name: "Note" })).toHaveAccessibleDescription("Legacy help.");
  expect(screen.queryByText("Time in seconds (5 minutes = 300).")).not.toBeInTheDocument();
  expect(screen.queryByText("Detailed toggle information.")).not.toBeInTheDocument();
  expect(screen.queryByText("Wrap *words* in asterisks. Full agent description.")).not.toBeInTheDocument();
});

it("shows only the selected enum option's help and updates it with the selection", async () => {
  const user = userEvent.setup();
  const fields = fieldsOf({ properties: { style: {
    type: "string", title: "Style", enum: ["ring", "bar", "big"], default: "ring",
    description: "Long explanation of all three styles.", "x-help": "General style help.",
    "x-option-help": { ring: "A circle that empties.", bar: "A bar that shrinks." },
  } } });
  function HelpForm() {
    const [values, setValues] = useState<Params>({ style: "ring" });
    return <SchemaForm fields={fields} values={values} onChange={(key, value) => setValues({ [key]: value })} />;
  }
  render(<HelpForm />);
  const group = screen.getByRole("radiogroup", { name: "Style" });
  expect(group).toHaveAccessibleDescription("A circle that empties.");
  expect(screen.queryByText("A bar that shrinks.")).not.toBeInTheDocument();
  await user.click(within(group).getByRole("radio", { name: "Bar" }));
  expect(group).toHaveAccessibleDescription("A bar that shrinks.");
  expect(screen.queryByText("A circle that empties.")).not.toBeInTheDocument();
  await user.click(within(group).getByRole("radio", { name: "Big" }));
  expect(group).not.toHaveAttribute("aria-describedby");
  expect(screen.queryByText("General style help.")).not.toBeInTheDocument();
  expect(screen.queryByText("Long explanation of all three styles.")).not.toBeInTheDocument();
});
