import "@testing-library/jest-dom/vitest";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Button } from "./button";
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
        <Button variant="destructive" size="sm">
          Destructive Small
        </Button>
      );
      expect(screen.getByRole("button")).toHaveClass("bg-destructive");

      rerender(
        <Button variant="outline" size="lg">
          Outline Large
        </Button>
      );
      expect(screen.getByRole("button")).toHaveClass("border");

      rerender(
        <Button variant="secondary" size="icon">
          Icon Secondary
        </Button>
      );
      expect(screen.getByRole("button")).toHaveClass("bg-secondary");

      rerender(<Button variant="ghost">Ghost</Button>);
      expect(screen.getByRole("button")).toHaveClass("hover:bg-accent");

      rerender(<Button variant="link">Link</Button>);
      expect(screen.getByRole("button")).toHaveClass("underline-offset-4");
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
                <Button variant="outline">Cancel</Button>
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
});
