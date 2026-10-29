import { useState } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { uploadImage, validateImage, MAX_IMAGE_BYTES } from "../api";
import { fieldsOf } from "../schemaForm";
import { ImageWidget } from "./media";
vi.mock("../api", async (original) => ({ ...await original<typeof import("../api")>(), uploadImage: vi.fn() }));
const field = fieldsOf({ properties: { photo: { "x-widget": "image", "x-crop": "circle", "x-shape": "circle", title: "Photo", anyOf: [{ type: "string" }, { type: "null" }] } } })[0];
function Photo({ initial = null }: { initial?: string | null }) { const [value, setValue] = useState<unknown>(initial); return <><ImageWidget field={field} id="photo" value={value} onChange={setValue} invalid={false} /><output>{String(value)}</output></>; }
function loaded() { const image = screen.getByAltText("Photo to crop"); Object.defineProperties(image, { naturalWidth: { value: 1200 }, naturalHeight: { value: 800 } }); fireEvent.load(image); }
function canvas() { vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ beginPath() {}, arc() {}, clip() {}, drawImage() {} } as unknown as CanvasRenderingContext2D); vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation((cb) => cb(new Blob(["cropped"]))); }

it("validates file extension and the backend's size limit before uploading", () => {
  expect(validateImage(new File(["ok"], "portrait.JPG"))).toBeNull();
  expect(validateImage(new File(["bad"], "document.pdf"))).toMatch(/PNG, JPG/);
  const large = new File(["x"], "huge.png"); Object.defineProperty(large, "size", { value: MAX_IMAGE_BYTES + 1 });
  expect(validateImage(large)).toMatch(/50 MB/); expect(validateImage(new File([], "empty.png"))).toMatch(/empty/);
});
it("shows drag, uploading filename, failed retry, crop, and the completed image actions", async () => {
  const user = userEvent.setup(); const upload = vi.mocked(uploadImage); upload.mockReset();
  let reject!: (error: Error) => void;
  upload.mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail; }));
  const { container } = render(<Photo />); const zone = container.querySelector(".studio-image-upload")!;
  fireEvent.dragOver(zone); expect(zone).toHaveAttribute("data-dragging", "true");
  const file = new File(["photo"], "portrait.jpg", { type: "image/jpeg" });
  fireEvent.drop(zone, { dataTransfer: { files: [file] } });
  expect(screen.getByRole("status", { name: "Uploading portrait.jpg" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Upload" })).toBeDisabled();
  await act(async () => reject(new Error("Connection lost")));
  expect(screen.getByRole("alert")).toHaveTextContent("Connection lost");
  upload.mockResolvedValueOnce("portrait.jpg");
  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(upload).toHaveBeenLastCalledWith(file);
  expect(await screen.findByRole("dialog", { name: "Adjust photo" })).toBeInTheDocument();
  expect(screen.getByText("null", { selector: "output" })).toBeInTheDocument();
  loaded(); canvas(); upload.mockResolvedValueOnce("portrait-crop.png");
  const position = screen.getByRole("group", { name: "Photo position" }); position.focus(); await user.keyboard("{Shift>}{ArrowLeft}{/Shift}");
  fireEvent.change(screen.getByLabelText(/Zoom/), { target: { value: "2" } });
  await user.click(screen.getByRole("button", { name: "Use photo" }));
  expect(await screen.findByRole("button", { name: "Adjust" })).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("portrait-crop.png");
  expect(screen.getByRole("button", { name: "Replace" })).toBeEnabled();
  expect(upload.mock.calls[2][0]).toMatchObject({ name: "portrait-crop.png", type: "image/png" });
  await user.click(screen.getByRole("button", { name: "Remove photo" }));
  expect(screen.getByRole("status")).toHaveTextContent("null");
});
it("keeps the previous picture on crop cancel and retries a failed cropped upload", async () => {
  const user = userEvent.setup(); const upload = vi.mocked(uploadImage); upload.mockReset();
  render(<Photo initial="existing.png" />);
  await user.click(screen.getByRole("button", { name: "Adjust" })); loaded(); canvas();
  upload.mockRejectedValueOnce(new Error("Couldn't save photo"));
  await user.click(screen.getByRole("button", { name: "Use photo" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't save photo");
  expect(screen.getByText("existing.png", { selector: "output" })).toBeInTheDocument();
  upload.mockResolvedValueOnce("adjusted.png"); await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("adjusted.png", { selector: "output" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Adjust" }));
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.getByRole("status")).toHaveTextContent("adjusted.png");
});
