import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ShaderPage } from "./ShaderPage";
import { SHADER_DRAFT_KEY, type ShaderDraft } from "./files";

vi.mock("./Preview", () => ({ ShaderPreview: ({ draft, onReady }: { draft: ShaderDraft; onReady: () => void }) => {
  useEffect(onReady, [onReady]);
  return <output aria-label="Rendered parameters">{JSON.stringify(draft)}</output>;
} }));

beforeEach(() => { localStorage.clear(); });

function rendered(): ShaderDraft { return JSON.parse(screen.getByLabelText("Rendered parameters").textContent!); }

describe("shader workspace", () => {
  it("flushes a just-edited draft when leaving the tab before autosave runs", () => {
    const view = render(<ShaderPage />);
    fireEvent.change(screen.getByRole("slider", { name: "Speed" }), { target: { value: "0.73" } });
    view.unmount();
    expect(JSON.parse(localStorage.getItem(SHADER_DRAFT_KEY)!).params.speed).toBe(0.73);
  });
  it("finds and filters the full collection, with a useful empty state", async () => {
    const user = userEvent.setup();
    render(<ShaderPage />);
    expect(screen.getByRole("combobox", { name: "Canvas format" })).toHaveValue("Landscape");
    expect(screen.getByRole("combobox", { name: "Fit" })).toHaveValue("contain");
    const library = within(screen.getByRole("group", { name: "Choose a shader" }));
    expect(library.getAllByRole("button")).toHaveLength(30);
    await user.click(screen.getByRole("button", { name: "Image filters" }));
    expect(library.getAllByRole("button")).toHaveLength(7);
    await user.type(screen.getByRole("searchbox", { name: "Search shaders" }), "glass");
    expect(library.getAllByRole("button")).toHaveLength(1);
    await user.type(screen.getByRole("searchbox", { name: "Search shaders" }), "missing");
    expect(screen.getByText("No shaders found.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show all shaders" }));
    expect(library.getAllByRole("button")).toHaveLength(30);
  });

  it("updates the rendered controls, restores edits when switching effects, and resets a shader", async () => {
    const user = userEvent.setup();
    render(<ShaderPage />);
    fireEvent.change(screen.getByRole("slider", { name: "Speed" }), { target: { value: "0.45" } });
    expect(rendered().params.speed).toBe(0.45);
    expect(screen.getByRole("spinbutton", { name: "Speed value" })).toHaveValue(45);
    expect(screen.getByText("Customized")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Water" }));
    expect(rendered().shader).toBe("water");
    await user.click(screen.getByRole("button", { name: "Slow-mo" }));
    expect(rendered().params.speed).toBe(0.1);
    expect(rendered().image).toBe("/shaders/flowers.webp");
    await user.click(screen.getByRole("button", { name: "Mesh Gradient" }));
    expect(rendered().params.speed).toBe(0.45);
    await user.click(screen.getByRole("button", { name: "Reset" }));
    expect(rendered().params.speed).toBe(1);
    await waitFor(() => expect(JSON.parse(localStorage.getItem(SHADER_DRAFT_KEY)!)).toMatchObject({ shader: "mesh-gradient", params: { speed: 1 } }));
  });

  it("enables optional groups and keeps numeric values in their actual units", async () => {
    const user = userEvent.setup();
    render(<ShaderPage />);
    await user.click(screen.getByRole("button", { name: "Paper Texture" }));
    expect(rendered().params.crumples).toBe(0);
    await user.click(screen.getByRole("checkbox", { name: "Enable crumples" }));
    expect(rendered().params.crumples).toBe(0.4);
    fireEvent.change(screen.getByRole("slider", { name: "Angle" }), { target: { value: "225" } });
    expect(rendered().params.angle).toBe(225);
    await user.click(screen.getByRole("checkbox", { name: "Enable crumples" }));
    expect(rendered().params.crumples).toBe(0);
    expect(screen.queryByRole("button", { name: "Export video" })).not.toBeInTheDocument();
  });

  it("restores an uploaded image when choosing a preset and shares it with other filters", async () => {
    const user = userEvent.setup();
    const { getShader } = await import("./catalog");
    const { newDraft } = await import("./files");
    localStorage.setItem(SHADER_DRAFT_KEY, JSON.stringify({ ...newDraft(getShader("water")!), image: "/assets/saved.png" }));
    render(<ShaderPage />);
    expect(rendered().image).toBe("/assets/saved.png");
    await user.click(screen.getByRole("button", { name: "Streaming" }));
    expect(rendered().image).toBe("/assets/saved.png");
    await user.click(screen.getByRole("button", { name: "Fluted Glass" }));
    expect(rendered().image).toBe("/assets/saved.png");
    await user.click(screen.getByRole("button", { name: "Use example image" }));
    expect(rendered().image).toBe("/shaders/flowers.webp");
  });
});
