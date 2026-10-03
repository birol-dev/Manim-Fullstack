import "@testing-library/jest-dom/vitest";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { Button } from "./button";
import { Field, Input, Textarea } from "./input";
import { Callout, EmptyState, Kbd, Section } from "./panel";
import { Segmented } from "./segmented";
import { Switch } from "./switch";
import { Progress } from "./progress";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "./tabs";
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from "./dialog";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  SelectGroup,
  SelectLabel,
  SelectSeparator,
} from "./select";

describe("UI Components", () => {
  describe("Button Component", () => {
    it("renders with default variant and handles clicks", async () => {
      const user = userEvent.setup();
      const handleClick = vi.fn();
      render(<Button onClick={handleClick}>Click Me</Button>);

      const btn = screen.getByRole("button", { name: "Click Me" });
      expect(btn).toBeInTheDocument();
      await user.click(btn);
      expect(handleClick).toHaveBeenCalledTimes(1);
    });

    it("renders all variants and sizes correctly", () => {
      const { rerender } = render(
        <Button variant="danger" size="xs">
          Danger
        </Button>,
      );
      expect(screen.getByRole("button")).toHaveClass("bg-danger", "h-6");
      expect(screen.getByRole("button")).toHaveAttribute("type", "button");

      rerender(<Button variant="primary" size="md">Primary</Button>);
      expect(screen.getByRole("button")).toHaveClass("bg-accent", "h-8");

      rerender(<Button variant="ghost" size="icon">Icon</Button>);
      expect(screen.getByRole("button")).toHaveClass("size-8");

      rerender(<Button variant="danger-ghost" size="icon-xs">x</Button>);
      expect(screen.getByRole("button")).toHaveClass("hover:text-danger", "size-6");

      rerender(<Button>Default</Button>);
      expect(screen.getByRole("button")).toHaveClass("bg-raised", "h-7");

      rerender(<Button type="submit">Submit</Button>);
      expect(screen.getByRole("button")).toHaveAttribute("type", "submit");
    });

    it("supports asChild rendering", () => {
      render(
        <Button asChild>
          <a href="/test">Link Button</a>
        </Button>
      );
      const link = screen.getByRole("link", { name: "Link Button" });
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute("href", "/test");
    });

    it("respects disabled state", async () => {
      const user = userEvent.setup();
      const handleClick = vi.fn();
      render(
        <Button disabled onClick={handleClick}>
          Disabled
        </Button>
      );
      const btn = screen.getByRole("button", { name: "Disabled" });
      expect(btn).toBeDisabled();
      await user.click(btn);
      expect(handleClick).not.toHaveBeenCalled();
    });
  });

  describe("Progress Component", () => {
    it("renders correctly with given progress value", () => {
      const { container } = render(<Progress value={45} className="custom-progress" />);
      const progressRoot = container.firstChild as HTMLElement;
      expect(progressRoot).toHaveClass("custom-progress");
      const indicator = progressRoot.querySelector("div");
      expect(indicator).toHaveStyle({ transform: "translateX(-55%)" });
      expect(indicator).not.toHaveClass("progress-stripes");
    });

    it("can show animated stripes", () => {
      const { container } = render(<Progress value={10} striped />);
      expect((container.firstChild as HTMLElement).querySelector("div")).toHaveClass("progress-stripes");
    });

    it("handles null/undefined value gracefully", () => {
      const { container } = render(<Progress value={undefined} />);
      const progressRoot = container.firstChild as HTMLElement;
      const indicator = progressRoot.querySelector("div");
      expect(indicator).toHaveStyle({ transform: "translateX(-100%)" });
    });
  });

  describe("Tabs Component", () => {
    it("renders tabs and switches active tab on click", async () => {
      const user = userEvent.setup();
      render(
        <Tabs defaultValue="tab1">
          <TabsList>
            <TabsTrigger value="tab1">Tab 1</TabsTrigger>
            <TabsTrigger value="tab2">Tab 2</TabsTrigger>
          </TabsList>
          <TabsContent value="tab1">Content 1</TabsContent>
          <TabsContent value="tab2">Content 2</TabsContent>
        </Tabs>
      );

      expect(screen.getByText("Content 1")).toBeInTheDocument();
      expect(screen.queryByText("Content 2")).not.toBeInTheDocument();

      const tab2Trigger = screen.getByRole("tab", { name: "Tab 2" });
      await user.click(tab2Trigger);

      expect(screen.getByText("Content 2")).toBeInTheDocument();
      expect(screen.queryByText("Content 1")).not.toBeInTheDocument();
    });
  });

  describe("Dialog Component", () => {
    it("opens and closes dialog with headers and footers", async () => {
      const user = userEvent.setup();
      render(
        <Dialog>
          <DialogTrigger asChild>
            <Button>Open Dialog</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Dialog Title</DialogTitle>
              <DialogDescription>Dialog Description</DialogDescription>
            </DialogHeader>
            <div>Body Content</div>
            <DialogFooter>
              <DialogClose asChild>
                <Button variant="ghost">Cancel</Button>
              </DialogClose>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      );

      expect(screen.queryByText("Dialog Title")).not.toBeInTheDocument();

      const openBtn = screen.getByRole("button", { name: "Open Dialog" });
      await user.click(openBtn);

      expect(screen.getByText("Dialog Title")).toBeInTheDocument();
      expect(screen.getByText("Dialog Description")).toBeInTheDocument();
      expect(screen.getByText("Body Content")).toBeInTheDocument();

      const cancelBtn = screen.getByRole("button", { name: "Cancel" });
      await user.click(cancelBtn);

      expect(screen.queryByText("Dialog Title")).not.toBeInTheDocument();
    });
  });

  describe("Select Component", () => {
    it("renders select items with group, label, and separator", async () => {
      const user = userEvent.setup();
      render(
        <Select defaultValue="apple">
          <SelectTrigger aria-label="Fruit">
            <SelectValue placeholder="Select a fruit" />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectLabel>Fruits</SelectLabel>
              <SelectItem value="apple">Apple</SelectItem>
              <SelectItem value="banana">Banana</SelectItem>
              <SelectSeparator />
              <SelectItem value="cherry">Cherry</SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
      );

      const trigger = screen.getByRole("combobox", { name: "Fruit" });
      expect(trigger).toBeInTheDocument();
      expect(trigger).toHaveTextContent("Apple");

      await user.click(trigger);
      expect(screen.getByText("Fruits")).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Banana" })).toBeInTheDocument();

      await user.click(screen.getByRole("option", { name: "Banana" }));
      expect(trigger).toHaveTextContent("Banana");
    });
  });

  describe("Switch", () => {
    it("toggles and reflects aria-checked", async () => {
      const user = userEvent.setup();
      function Harness() {
        const [on, setOn] = useState(false);
        return <Switch checked={on} onCheckedChange={setOn} aria-label="Loop" />;
      }
      render(<Harness />);
      const toggle = screen.getByRole("switch", { name: "Loop" });
      expect(toggle).toHaveAttribute("aria-checked", "false");
      await user.click(toggle);
      expect(toggle).toHaveAttribute("aria-checked", "true");
    });

    it("does nothing when disabled", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(<Switch checked={false} onCheckedChange={onChange} disabled aria-label="Off" />);
      await user.click(screen.getByRole("switch"));
      expect(onChange).not.toHaveBeenCalled();
    });
  });

  describe("Segmented", () => {
    it("selects options as radios", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      render(
        <Segmented
          aria-label="Storage"
          value="a"
          onChange={onChange}
          options={[
            { value: "a", label: "Alpha" },
            { value: "b", label: "Beta" },
          ]}
        />,
      );
      expect(screen.getByRole("radiogroup", { name: "Storage" })).toBeInTheDocument();
      expect(screen.getByRole("radio", { name: "Alpha" })).toHaveAttribute("aria-checked", "true");
      await user.click(screen.getByRole("radio", { name: "Beta" }));
      expect(onChange).toHaveBeenCalledWith("b");
    });
  });

  describe("Field, Input, Textarea", () => {
    it("labels controls and shows hints or errors", () => {
      const { rerender } = render(
        <Field label="Name" htmlFor="name" hint="Lowercase works best">
          <Input id="name" />
        </Field>,
      );
      expect(screen.getByLabelText("Name")).toBeInTheDocument();
      expect(screen.getByText("Lowercase works best")).toBeInTheDocument();

      rerender(
        <Field label="Notes" htmlFor="notes" hint="ignored" error="Too long">
          <Textarea id="notes" />
        </Field>,
      );
      expect(screen.getByRole("alert")).toHaveTextContent("Too long");
      expect(screen.queryByText("ignored")).not.toBeInTheDocument();
    });
  });

  describe("Panel helpers", () => {
    it("renders sections, empty states, callouts, and keys", () => {
      render(
        <>
          <Section title="Scripts" actions={<button>Add</button>}>
            <p>content</p>
          </Section>
          <EmptyState title="Nothing here" description="Add something" action={<button>Go</button>} />
          <Callout tone="danger">Broken</Callout>
          <Kbd>Ctrl</Kbd>
        </>,
      );
      expect(screen.getByRole("heading", { name: "Scripts" })).toBeInTheDocument();
      expect(screen.getByText("Nothing here")).toBeInTheDocument();
      expect(screen.getByText("Broken").parentElement).toHaveClass("bg-danger-soft");
      expect(screen.getByText("Ctrl").tagName).toBe("KBD");
    });
  });
});
