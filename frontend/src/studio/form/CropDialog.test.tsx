import { useState } from "react";
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

/** Pointer capture plus a screen size for the crop window, so drags have real pixels. */
function pointerSession(mask: HTMLElement, size = 150) {
  vi.spyOn(mask, "getBoundingClientRect").mockReturnValue({ left: 0, top: 0, width: size, height: size } as DOMRect);
  let captured = false;
  vi.spyOn(mask, "setPointerCapture").mockImplementation(() => { captured = true; });
  vi.spyOn(mask, "hasPointerCapture").mockImplementation(() => captured);
  vi.spyOn(mask, "releasePointerCapture").mockImplementation(() => { captured = false; });
  return (type: string, clientX: number, clientY = 100) => {
    const event = new Event(type, { bubbles: true });
    Object.assign(event, { button: 0, pointerId: 1, clientX, clientY });
    fireEvent(mask, event);
  };
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
  const mask = screen.getByRole("group", { name: "Photo position" });
  expect(parseFloat(mask.style.width)).toBeCloseTo(22.22, 1);
  expect(parseFloat(mask.style.height)).toBeCloseTo(33.33, 1);
  await user.click(screen.getByRole("button", { name: "Reset" }));
  expect(screen.getByRole("slider", { name: "Crop width" })).toHaveValue("1.5");
  expect(screen.getByRole("slider", { name: "Zoom" })).toHaveValue("1");
  expect(parseFloat(mask.style.width)).toBeCloseTo(100, 5);
  await user.click(screen.getByRole("button", { name: "Use photo" }));
  expect(canvas.drawImage).toHaveBeenCalledWith(image, 0, 0, 1200, 800, 0, 0, 1200, 800);
  expect(confirm.mock.calls[0][0]).toMatchObject({ name: "portrait-crop.png", type: "image/png" });
});

it("shows the whole photo in the stage with the mask as a hole over it", () => {
  render(<CropDialog name="portrait.jpg" shape="circle" onClose={() => {}} onConfirm={vi.fn()} />);
  const photo = loadPhoto();
  const mask = screen.getByRole("group", { name: "Photo position" });
  const frame = photo.parentElement!;
  expect(frame).toHaveClass("studio-crop-frame");
  expect(frame).toContainElement(photo);
  expect(frame).toContainElement(mask);
  expect(mask).not.toContainElement(photo);
  expect(photo).toHaveClass("studio-crop-photo");
  expect(mask).toHaveClass("studio-crop-mask");
  expect(mask).toHaveAttribute("data-circle", "true");
  expect(mask).toHaveFocus();
  expect(frame).toHaveStyle({ aspectRatio: "1.5" });
  expect(parseFloat(mask.style.left)).toBeCloseTo(16.67, 1);
  expect(parseFloat(mask.style.width)).toBeCloseTo(66.67, 1);
  expect(parseFloat(mask.style.height)).toBeCloseTo(100, 5);
});

it("moves the crop window right and up with the arrow keys and Escape closes", async () => {
  const user = userEvent.setup();
  const close = vi.fn();
  const confirm = vi.fn().mockResolvedValue(undefined);
  render(<CropDialog name="original.jpg" shape="circle" onClose={close} onConfirm={confirm} />);
  loadPhoto();
  mockCanvas();
  const mask = screen.getByRole("group", { name: "Photo position" });
  expect(mask).toHaveFocus();
  fireEvent.change(screen.getByRole("slider", { name: "Zoom" }), { target: { value: "2" } });
  const left = parseFloat(mask.style.left);
  const top = parseFloat(mask.style.top);
  await user.keyboard("{ArrowRight}{Shift>}{ArrowUp}{/Shift}");
  expect(parseFloat(mask.style.left)).toBeGreaterThan(left);
  expect(parseFloat(mask.style.top)).toBeLessThan(top);
  await user.click(screen.getByRole("button", { name: "Use photo" }));
  expect(confirm.mock.calls[0][1].position).toEqual({ x: .02, y: -.1, zoom: 2 });
  await user.keyboard("{Escape}");
  expect(close).toHaveBeenCalledOnce();
});

it("clamps the crop window inside the photo when a drag overshoots", async () => {
  const user = userEvent.setup();
  render(<CropDialog name="portrait.jpg" shape="circle" onClose={() => {}} onConfirm={vi.fn().mockResolvedValue(undefined)} />);
  const image = loadPhoto();
  const canvas = mockCanvas();
  const mask = screen.getByRole("group", { name: "Photo position" });
  const pointer = pointerSession(mask);
  fireEvent.change(screen.getByRole("slider", { name: "Zoom" }), { target: { value: "2" } });
  act(() => { pointer("pointerdown", 150); pointer("pointermove", -900); pointer("pointerup", -900); });
  expect(parseFloat(mask.style.left)).toBe(0);
  await user.click(screen.getByRole("button", { name: "Use photo" }));
  expect(canvas.drawImage).toHaveBeenCalledWith(image, 0, 200, 400, 400, 0, 0, 400, 400);
  expect(screen.queryByRole("slider", { name: "Crop width" })).not.toBeInTheDocument();
});

it("follows the pointer: a 60 px drag right moves the window 60 px right", async () => {
  const user = userEvent.setup();
  render(<CropDialog name="portrait.jpg" shape="circle" onClose={() => {}} onConfirm={vi.fn().mockResolvedValue(undefined)} />);
  const image = loadPhoto();
  const canvas = mockCanvas();
  const mask = screen.getByRole("group", { name: "Photo position" });
  const pointer = pointerSession(mask);
  fireEvent.change(screen.getByRole("slider", { name: "Zoom" }), { target: { value: "2" } });
  const before = parseFloat(mask.style.left);
  act(() => { pointer("pointerdown", 150); pointer("pointermove", 210); pointer("pointerup", 210); });
  // At zoom 2 the 400 px crop window is a quarter of the 1200 px photo, drawn 150 px wide here.
  expect((parseFloat(mask.style.left) - before) / 100 * 1200 * (150 / 400)).toBeCloseTo(60, 6);
  await user.click(screen.getByRole("button", { name: "Use photo" }));
  expect(canvas.drawImage).toHaveBeenCalledWith(image, 560, 200, 400, 400, 0, 0, 400, 400);
});

it("clamps the crop window at the photo edge when arrow keys push past it", async () => {
  const user = userEvent.setup();
  const confirm = vi.fn().mockResolvedValue(undefined);
  render(<CropDialog name="portrait.jpg" shape="circle" initialCrop={{ source: "portrait.jpg", position: { x: 1, y: -1, zoom: 1 }, ratio: 1, shape: "circle" }}
    onClose={() => {}} onConfirm={confirm} />);
  loadPhoto();
  mockCanvas();
  const mask = screen.getByRole("group", { name: "Photo position" });
  expect(mask).toHaveAttribute("aria-valuetext", "Top right");
  await user.keyboard("{ArrowRight}{ArrowUp}");
  expect(mask).toHaveAttribute("aria-valuetext", "Top right");
  await user.click(screen.getByRole("button", { name: "Use photo" }));
  expect(confirm.mock.calls[0][1].position).toEqual({ x: 1, y: -1, zoom: 1 });
});

it("reopens a saved crop in the same place and returns the same position", async () => {
  const user = userEvent.setup();
  const confirm = vi.fn().mockResolvedValue(undefined);
  render(<CropDialog name="portrait.jpg" shape="circle" initialCrop={{ source: "portrait.jpg", position: { x: .3, y: -.2, zoom: 2 }, ratio: 1, shape: "circle" }}
    onClose={() => {}} onConfirm={confirm} />);
  loadPhoto();
  mockCanvas();
  const mask = screen.getByRole("group", { name: "Photo position" });
  // 1200x800, circle at zoom 2: a 400x400 window, positioned 30% / -20% across its travel.
  expect(parseFloat(mask.style.left)).toBeCloseTo(43.33, 2);
  expect(parseFloat(mask.style.top)).toBeCloseTo(20, 5);
  await user.click(screen.getByRole("button", { name: "Use photo" }));
  expect(confirm.mock.calls[0][1]).toEqual({
    source: "portrait.jpg", position: { x: .3, y: -.2, zoom: 2 }, ratio: 1, shape: "circle",
  });
});

it("exports exactly the region the crop window shows", async () => {
  const user = userEvent.setup();
  const confirm = vi.fn().mockResolvedValue(undefined);
  render(<CropDialog name="portrait.jpg" shape="16:9" onClose={() => {}} onConfirm={confirm} />);
  loadPhoto();
  const canvas = mockCanvas();
  const mask = screen.getByRole("group", { name: "Photo position" });
  fireEvent.change(screen.getByRole("slider", { name: "Zoom" }), { target: { value: "1.5" } });
  mask.focus();
  await user.keyboard("{ArrowRight}{ArrowRight}{ArrowRight}{ArrowDown}{ArrowDown}");
  const shown = {
    x: parseFloat(mask.style.left) / 100 * 1200,
    y: parseFloat(mask.style.top) / 100 * 800,
    width: parseFloat(mask.style.width) / 100 * 1200,
    height: parseFloat(mask.style.height) / 100 * 800,
  };
  await user.click(screen.getByRole("button", { name: "Use photo" }));
  const draw = canvas.drawImage.mock.calls[0];
  expect(draw[1]).toBeCloseTo(shown.x, 6);
  expect(draw[2]).toBeCloseTo(shown.y, 6);
  expect(draw[3]).toBeCloseTo(shown.width, 6);
  expect(draw[4]).toBeCloseTo(shown.height, 6);
  expect(draw[5]).toBe(0);
  expect(draw[6]).toBe(0);
  expect(draw[7]).toBe(Math.round(shown.width));
  expect(draw[8]).toBe(Math.round(shown.height));
  expect(confirm.mock.calls[0][1].ratio).toBeCloseTo(16 / 9);
});

it("uses the circle/frame wording and names where the window is", async () => {
  const user = userEvent.setup();
  const view = render(<CropDialog name="portrait.jpg" shape="circle" onClose={() => {}} onConfirm={vi.fn()} />);
  loadPhoto();
  expect(screen.getByRole("dialog", { name: "Adjust photo" })).toHaveAccessibleDescription(
    "Drag the circle to choose what shows in your video. Arrow keys move it too.");
  expect(screen.getByText("Shift + arrow moves farther.")).toBeInTheDocument();
  const mask = screen.getByRole("group", { name: "Photo position" });
  expect(mask).toHaveAttribute("aria-valuetext", "Center");
  await user.keyboard("{Shift>}{ArrowRight}{ArrowRight}{ArrowRight}{ArrowRight}{/Shift}");
  expect(mask).toHaveAttribute("aria-valuetext", "Right");
  view.unmount();
  render(<CropDialog name="portrait.jpg" shape="16:9" onClose={() => {}} onConfirm={vi.fn()} />);
  expect(screen.getByRole("dialog", { name: "Adjust photo" })).toHaveAccessibleDescription(
    "Drag the frame to choose what shows in your video. Arrow keys move it too.");
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
