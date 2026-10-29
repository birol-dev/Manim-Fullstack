import { useState } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { getImageInfo, saveImageCrop, uploadImage, validateImage, MAX_IMAGE_BYTES } from "../api";
import type { ImageCropRecipe } from "../types";
import { fieldsOf } from "../schemaForm";
import { ImageWidget } from "./media";
vi.mock("../api", async (original) => ({ ...await original<typeof import("../api")>(), uploadImage: vi.fn(), getImageInfo: vi.fn(), saveImageCrop: vi.fn() }));
beforeEach(() => {
  vi.mocked(getImageInfo).mockReset().mockImplementation(async (name) => ({ name, crop: null }));
  vi.mocked(saveImageCrop).mockReset().mockImplementation(async (name, crop) => ({ name, crop }));
});
const field = fieldsOf({ properties: { photo: { "x-widget": "image", "x-crop": "circle", "x-shape": "circle", title: "Photo", anyOf: [{ type: "string" }, { type: "null" }] } } })[0];
function Photo({ initial = null }: { initial?: string | null }) { const [value, setValue] = useState<unknown>(initial); return <><ImageWidget field={field} id="photo" value={value} onChange={setValue} invalid={false} /><output>{String(value)}</output></>; }
function loaded(width = 1200, height = 800) { const image = screen.getByAltText("Photo to crop"); Object.defineProperties(image, { naturalWidth: { value: width }, naturalHeight: { value: height } }); fireEvent.load(image); }
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

it("reopens the original with the saved crop after a reload and crops from it again", async () => {
  const user = userEvent.setup();
  const upload = vi.mocked(uploadImage).mockReset();
  const recipe: ImageCropRecipe = { source: "test_photo.jpg", position: { x: .5, y: -.5, zoom: 2 }, ratio: 1, shape: "circle" };
  // Metadata is returned by the workspace API, independently of component state.
  vi.mocked(getImageInfo).mockResolvedValue({ name: "test_photo-crop.png", crop: recipe });
  const view = render(<Photo initial="test_photo-crop.png" />);
  await user.click(screen.getByRole("button", { name: "Adjust" }));
  expect(getImageInfo).toHaveBeenCalledWith("test_photo-crop.png");
  const image = await screen.findByAltText("Photo to crop");
  expect(image).toHaveAttribute("src", "/assets/test_photo.jpg");
  loaded(); canvas();
  expect(screen.getByRole("slider", { name: "Zoom" })).toHaveValue("2");
  const stage = screen.getByRole("group", { name: "Photo position" });
  expect(stage).toHaveFocus();
  expect(parseFloat(stage.style.left)).toBeCloseTo(50, 4);
  expect(parseFloat(stage.style.top)).toBeCloseTo(12.5, 4);
  upload.mockResolvedValueOnce("test_photo-crop-new.png");
  await user.keyboard("{Shift>}{ArrowRight}{/Shift}");
  await user.click(screen.getByRole("button", { name: "Use photo" }));
  expect(saveImageCrop).toHaveBeenCalledWith("test_photo-crop-new.png", { ...recipe, position: { ...recipe.position, x: .6 } });
  expect(upload.mock.calls[0][0].name).toBe("test_photo-crop.png");
  expect(screen.getByRole("status")).toHaveTextContent("test_photo-crop-new.png");
  view.unmount();
  render(<Photo initial="test_photo-crop.png" />);
  await user.click(screen.getByRole("button", { name: "Adjust" }));
  expect(await screen.findByAltText("Photo to crop")).toHaveAttribute("src", "/assets/test_photo.jpg");
  expect(screen.getByRole("slider", { name: "Zoom" })).toHaveValue("2");
});

it("starts directly from an MCP image without crop metadata and keeps the value on lookup failure", async () => {
  const user = userEvent.setup();
  render(<Photo initial="agent-photo.png" />);
  vi.mocked(getImageInfo).mockRejectedValueOnce(new Error("Server is offline"));
  await user.click(screen.getByRole("button", { name: "Adjust" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Server is offline");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("agent-photo.png");
  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByAltText("Photo to crop")).toHaveAttribute("src", "/assets/agent-photo.png");
  expect(screen.getByRole("slider", { name: "Zoom" })).toHaveValue("1");
});

it("does not select an uploaded crop until its workspace metadata is saved", async () => {
  const user = userEvent.setup();
  vi.mocked(uploadImage).mockReset().mockResolvedValue("new-crop.png");
  vi.mocked(saveImageCrop).mockRejectedValueOnce(new Error("Couldn't save crop settings"));
  render(<Photo initial="original.jpg" />);
  await user.click(screen.getByRole("button", { name: "Adjust" }));
  loaded(); canvas();
  await user.click(screen.getByRole("button", { name: "Use photo" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't save crop settings");
  expect(screen.getByText("original.jpg", { selector: "output" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(screen.getByRole("status")).toHaveTextContent("new-crop.png");
});

it("uses an uploaded SVG as is, without opening the crop dialog", async () => {
  const upload = vi.mocked(uploadImage).mockReset().mockResolvedValue("logo.svg");
  const { container } = render(<Photo />);
  const zone = container.querySelector(".studio-image-upload")!;
  fireEvent.drop(zone, { dataTransfer: { files: [new File(["<svg/>"], "logo.svg", { type: "image/svg+xml" })] } });
  await waitFor(() => expect(screen.getByText("logo.svg", { selector: "output" })).toBeInTheDocument());
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(upload).toHaveBeenCalledOnce();
  expect(saveImageCrop).not.toHaveBeenCalled();
});

it("offers no Adjust for an SVG, which is used as is", () => {
  render(<Photo initial="logo.svg" />);
  expect(screen.getByRole("status")).toHaveTextContent("logo.svg");
  expect(screen.queryByRole("button", { name: "Adjust" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Replace" })).toBeInTheDocument();
});

it("keeps the original picture when Use as is is chosen", async () => {
  const user = userEvent.setup();
  const upload = vi.mocked(uploadImage).mockReset();
  const recipe: ImageCropRecipe = { source: "test_photo.jpg", position: { x: .5, y: -.5, zoom: 2 }, ratio: 1, shape: "circle" };
  vi.mocked(getImageInfo).mockResolvedValue({ name: "test_photo-crop.png", crop: recipe });
  render(<Photo initial="test_photo-crop.png" />);
  await user.click(screen.getByRole("button", { name: "Adjust" }));
  await screen.findByRole("dialog", { name: "Adjust photo" });
  await user.click(screen.getByRole("button", { name: "Use as is" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.getByText("test_photo.jpg", { selector: "output" })).toBeInTheDocument();
  expect(upload).not.toHaveBeenCalled();
  expect(saveImageCrop).not.toHaveBeenCalled();
});

it.each(["the original was deleted", "the metadata record is gone"])("adjusts the current crop without errors when %s", async () => {
  const user = userEvent.setup();
  // Both cases return this same successful API response (covered by the backend tests).
  vi.mocked(getImageInfo).mockResolvedValue({ name: "test_photo-crop.png", crop: null });
  vi.mocked(uploadImage).mockReset().mockResolvedValueOnce("reframed.png");
  render(<Photo initial="test_photo-crop.png" />);
  await user.click(screen.getByRole("button", { name: "Adjust" }));
  expect(await screen.findByRole("dialog", { name: "Adjust photo" })).toBeInTheDocument();
  expect(screen.getByAltText("Photo to crop")).toHaveAttribute("src", "/assets/test_photo-crop.png");
  loaded(800, 800); canvas();
  const stage = screen.getByRole("group", { name: "Photo position" });
  expect(stage).toHaveFocus();
  expect(parseFloat(stage.style.left)).toBe(0);
  expect(parseFloat(stage.style.top)).toBe(0);
  expect(screen.getByRole("slider", { name: "Zoom" })).toHaveValue("1");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Use photo" }));
  expect(saveImageCrop).toHaveBeenCalledWith("reframed.png", {
    source: "test_photo-crop.png", position: { x: 0, y: 0, zoom: 1 }, ratio: 1, shape: "circle",
  });
  expect(screen.getByRole("status")).toHaveTextContent("reframed.png");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
