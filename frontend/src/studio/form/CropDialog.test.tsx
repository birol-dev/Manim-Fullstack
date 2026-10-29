import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { CropDialog } from "./CropDialog";

function loadPhoto() {
  const image = screen.getByAltText("Photo to crop");
  Object.defineProperties(image, { naturalWidth: { value: 1200 }, naturalHeight: { value: 800 } });
  fireEvent.load(image);
  return image;
}

function mockCanvas() {
  const context = { beginPath: vi.fn(), arc: vi.fn(), clip: vi.fn(), drawImage: vi.fn() };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation((callback) => callback(new Blob(["photo"], { type: "image/png" })));
  return context;
}

it("supports free crop width, zoom and Reset before exporting the chosen rectangle", async () => {
  const user = userEvent.setup();
  const confirm = vi.fn().mockResolvedValue(undefined);
  render(<CropDialog name="portrait.jpg" onClose={() => {}} onConfirm={confirm} />);
  expect(screen.getByRole("button", { name: "Use photo" })).toBeDisabled();
  const image = loadPhoto();
  const canvas = mockCanvas();
  fireEvent.change(screen.getByRole("slider", { name: "Crop width" }), { target: { value: "1" } });
  fireEvent.change(screen.getByRole("slider", { name: "Zoom" }), { target: { value: "3" } });
  expect(image).toHaveStyle({ width: "450%" });
  await user.click(screen.getByRole("button", { name: "Reset" }));
  expect(screen.getByRole("slider", { name: "Crop width" })).toHaveValue("1.5");
  expect(screen.getByRole("slider", { name: "Zoom" })).toHaveValue("1");
  await user.click(screen.getByRole("button", { name: "Use photo" }));
  expect(canvas.drawImage).toHaveBeenCalledWith(image, 0, 0, 1200, 800, 0, 0, 1200, 800);
  expect(confirm.mock.calls[0][0]).toMatchObject({ name: "portrait-crop.png", type: "image/png" });
});

it("keeps drag coordinates after pointerup and clamps the photo to the mask", async () => {
  const user = userEvent.setup();
  render(<CropDialog name="portrait.jpg" shape="circle" onClose={() => {}} onConfirm={vi.fn().mockResolvedValue(undefined)} />);
  const image = loadPhoto();
  const canvas = mockCanvas();
  const mask = screen.getByRole("group", { name: "Photo position" });
  vi.spyOn(mask, "getBoundingClientRect").mockReturnValue({ left: 0, top: 0, width: 300, height: 300 } as DOMRect);
  let captured = false;
  vi.spyOn(mask, "setPointerCapture").mockImplementation(() => { captured = true; });
  vi.spyOn(mask, "hasPointerCapture").mockImplementation(() => captured);
  vi.spyOn(mask, "releasePointerCapture").mockImplementation(() => { captured = false; });
  const pointer = (type: string, clientX: number) => {
    const event = new Event(type, { bubbles: true });
    Object.assign(event, { button: 0, pointerId: 1, clientX, clientY: 100 });
    fireEvent(mask, event);
  };
  fireEvent.change(screen.getByRole("slider", { name: "Zoom" }), { target: { value: "2" } });
  act(() => { pointer("pointerdown", 150); pointer("pointermove", -900); pointer("pointerup", -900); });
  await user.click(screen.getByRole("button", { name: "Use photo" }));
  expect(canvas.drawImage).toHaveBeenCalledWith(image, 800, 200, 400, 400, 0, 0, 400, 400);
  expect(screen.queryByRole("slider", { name: "Crop width" })).not.toBeInTheDocument();
});

it("retries a load failure, keeps a fixed slot aspect, and returns focus on cancel", async () => {
  const user = userEvent.setup();
  const close = vi.fn();
  function Photo() {
    const [open, setOpen] = useState(false);
    return <><button type="button" onClick={() => setOpen(true)}>Adjust</button>{open && <CropDialog name="photo.png" shape="16:9"
      onClose={() => { close(); setOpen(false); }} onConfirm={vi.fn()} />}</>;
  }
  render(<Photo />);
  await user.click(screen.getByRole("button", { name: "Adjust" }));
  fireEvent.error(screen.getByAltText("Photo to crop"));
  expect(screen.getByRole("alert")).toHaveTextContent("Couldn't open this picture");
  await user.click(screen.getByRole("button", { name: "Try again" }));
  loadPhoto();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByRole("group", { name: "Photo position" })).toHaveStyle({ aspectRatio: String(16 / 9) });
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(close).toHaveBeenCalledOnce();
  expect(screen.getByRole("button", { name: "Adjust" })).toHaveFocus();
});
import { useState } from "react";
