import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { NewFileDialog } from "./NewFileDialog";

function Harness({ onCreate, onCreatedFocus }: { onCreate: (name: string) => Promise<void>; onCreatedFocus: () => void }) {
  const [open, setOpen] = useState(true);
  return (
    <>
      <textarea aria-label="Editor" />
      <NewFileDialog
        request={open ? { suggestedName: "scene.py" } : null}
        existing={[]}
        onClose={() => setOpen(false)}
        onCreate={onCreate}
        onCreatedFocus={onCreatedFocus}
      />
    </>
  );
}

describe("NewFileDialog", () => {
  it("keeps the submitted name while the file is created, then hands focus over once", async () => {
    const user = userEvent.setup();
    let finish: () => void = () => {};
    const onCreate = vi.fn(() => new Promise<void>((resolve) => (finish = resolve)));
    const onCreatedFocus = vi.fn(() => screen.getByLabelText("Editor").focus());
    render(<Harness onCreate={onCreate} onCreatedFocus={onCreatedFocus} />);

    const input = screen.getByLabelText("File name");
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(onCreate).toHaveBeenCalledWith("scene.py");
    // Busy: what is typed now can't rename the file being created.
    expect(input).toHaveAttribute("readonly");
    await user.type(input, "zzz");
    expect(input).toHaveValue("scene.py");

    finish();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByLabelText("Editor")).toHaveFocus();
    // Not refocused when the dialog finishes closing (that would undo a click made meanwhile).
    expect(onCreatedFocus).toHaveBeenCalledTimes(1);
  });

  it("stays open with the error when creating fails", async () => {
    const user = userEvent.setup();
    const onCreatedFocus = vi.fn();
    render(<Harness onCreate={() => Promise.reject(new Error("scene.py already exists."))} onCreatedFocus={onCreatedFocus} />);
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByText("scene.py already exists.")).toBeInTheDocument();
    expect(screen.getByLabelText("File name")).not.toHaveAttribute("readonly");
    expect(onCreatedFocus).not.toHaveBeenCalled();
  });
});
