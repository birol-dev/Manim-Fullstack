import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { uploadAudio } from "./api";
import { SoundPanel } from "./SoundPanel";
import { DEFAULT_SOUND, volumeGain } from "./sound";
import { visualPreviewKey, stableKey } from "./preview";
import type { SoundSettings } from "./types";

vi.mock("./api", async (original) => ({ ...await original<typeof import("./api")>(), uploadAudio: vi.fn() }));
const tracks = [
  { id: "calm", title: "Quiet morning", description: "Warm notes", url: "/api/studio/sounds/music/calm.wav" },
  { id: "upbeat", title: "Small steps", description: "Steady pulse", url: "/api/studio/sounds/music/upbeat.wav" },
];
function Panel() {
  const [sound, setSound] = useState<SoundSettings>(structuredClone(DEFAULT_SOUND));
  return <><SoundPanel value={sound} onChange={setSound} tracks={tracks} /><output data-testid="sound">{JSON.stringify(sound)}</output></>;
}
const current = (): SoundSettings => JSON.parse(screen.getByTestId("sound").textContent!);

it("offers effects, music, fade, repeat and keyboard volume controls without losing other settings", async () => {
  const user = userEvent.setup();
  render(<Panel />);
  expect(screen.getByRole("switch", { name: "Sound effects" })).toBeChecked();
  await user.click(screen.getByRole("radio", { name: /Quiet morning/ }));
  expect(current().music).toMatchObject({ track: "calm", asset: null, fade_out: true, loop: true });
  fireEvent.change(screen.getByRole("slider", { name: "Music volume" }), { target: { value: "60" } });
  await user.click(screen.getByRole("switch", { name: "Fade out at the end" }));
  await user.click(screen.getByRole("switch", { name: "Repeat short music" }));
  await user.click(screen.getByRole("switch", { name: "Sound effects" }));
  expect(current()).toMatchObject({ effects: false, music: { track: "calm", volume: .6, fade_out: false, loop: false } });
  expect(screen.getByText(/Pictures and GIFs are always silent/)).toBeInTheDocument();
  await user.click(screen.getByRole("radio", { name: "None" }));
  expect(current().music).toMatchObject({ track: null, asset: null, volume: .6 });
});

it("auditions only after a click, at the mastered level, and stops from the same row", async () => {
  const play = vi.spyOn(HTMLMediaElement.prototype, "play");
  const user = userEvent.setup();
  render(<Panel />);
  expect(play).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Listen to Quiet morning" }));
  expect(play).toHaveBeenCalledTimes(1);
  const player = screen.getByLabelText("Quiet morning sample") as HTMLAudioElement;
  expect(player.src).toContain("/api/studio/sounds/music/calm.wav");
  expect(player.volume).toBe(1);
  expect(current().music.track).toBeNull();
  const stop = screen.getByRole("button", { name: "Stop Quiet morning" });
  expect(stop).toHaveAttribute("aria-pressed", "true");
  await user.click(stop);
  expect(screen.getByRole("button", { name: "Listen to Quiet morning" })).toHaveAttribute("aria-pressed", "false");
});

it("uses option cards with radio semantics, arrow navigation and a separate audition button", async () => {
  const user = userEvent.setup();
  const { container } = render(<Panel />);
  const none = screen.getByRole("radio", { name: "None" });
  expect(none).toHaveAttribute("tabindex", "0");
  expect(container.querySelector('input[type="radio"]')).toBeNull();
  expect(screen.getByRole("radiogroup", { name: "Music" })).toContainElement(none);
  none.focus();
  await user.keyboard("{ArrowDown}");
  const calm = screen.getByRole("radio", { name: "Quiet morning" });
  expect(calm).toHaveFocus();
  expect(calm).toHaveAttribute("aria-checked", "true");
  expect(calm).toHaveAccessibleDescription("Warm notes");
  expect(calm.closest(".studio-sound-option")).toHaveClass("studio-sound-selected");
  expect(calm.closest(".studio-sound-option")).toContainElement(screen.getByRole("button", { name: "Listen to Quiet morning" }));
  await user.keyboard("{End}");
  expect(screen.getByRole("radio", { name: "Your music" })).toHaveFocus();
  expect(current().music.track).toBeNull();
  await user.keyboard("{Home}");
  expect(none).toHaveAttribute("aria-checked", "true");
});

it("labels styled sliders with percentages and uses the same dB curve for auditions", async () => {
  const user = userEvent.setup();
  render(<Panel />);
  await user.click(screen.getByRole("radio", { name: "Quiet morning" }));
  const slider = screen.getByRole("slider", { name: "Music volume" });
  expect(slider).toHaveClass("studio-sound-range");
  expect(slider).toHaveAttribute("aria-valuetext", "100 percent");
  fireEvent.change(slider, { target: { value: "75" } });
  expect(slider).toHaveAttribute("aria-valuetext", "75 percent");
  expect(slider).toHaveStyle({ "--sound-fill": "75%" });
  slider.focus(); expect(slider).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "Listen to Quiet morning" }));
  expect((screen.getByLabelText("Quiet morning sample") as HTMLAudioElement).volume).toBeCloseTo(10 ** (-2.5 / 20));
  expect(volumeGain(0)).toBe(0);
  expect(volumeGain(.25)).toBeCloseTo(10 ** (-22.5 / 20));
  expect(volumeGain(.5)).toBeCloseTo(10 ** (-10 / 20));
  expect(volumeGain(1)).toBe(1);
});

it("shows upload progress and keeps edits made while the upload is preparing", async () => {
  const user = userEvent.setup();
  let complete!: (value: Awaited<ReturnType<typeof uploadAudio>>) => void;
  vi.mocked(uploadAudio).mockImplementationOnce((_file, progress) => {
    progress(54);
    return new Promise((resolve) => { complete = resolve; });
  });
  const { container } = render(<Panel />);
  await user.click(screen.getByRole("radio", { name: "Your music" }));
  await user.upload(container.querySelector('input[type="file"]')!, new File(["audio"], "My song.mp3", { type: "audio/mpeg" }));
  expect(screen.getByRole("progressbar", { name: "Music upload" })).toHaveAttribute("value", "54");
  await user.click(screen.getByRole("switch", { name: "Sound effects" }));
  complete({ name: `audio-${"a".repeat(32)}.wav`, title: "My song.mp3", duration: 1, url: "/audio" });
  await waitFor(() => expect(current().music.asset).toContain("audio-"));
  expect(current().effects).toBe(false);
  expect(current().music.track).toBeNull();
  expect(screen.getByText("My song.mp3")).toBeInTheDocument();
});

it("keeps old music when replacing it fails and reports a useful error", async () => {
  vi.mocked(uploadAudio).mockRejectedValueOnce(new Error("This audio couldn't be read."));
  const user = userEvent.setup();
  const { container } = render(<Panel />);
  await user.click(screen.getByRole("radio", { name: "Your music" }));
  await user.upload(container.querySelector('input[type="file"]')!, new File(["bad"], "bad.wav", { type: "audio/wav" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("couldn't be read");
  expect(current().music.asset).toBeNull();
  expect(screen.getByRole("button", { name: "Upload music" })).toBeEnabled();
});

it("sound changes leave visual preview keys alone while normal snapshots retain them", () => {
  const request = { template: "quote", params: { text: "Hello" }, settings: { sound: DEFAULT_SOUND }, mode: "poster" as const };
  const changed = { ...request, settings: { sound: { ...DEFAULT_SOUND, effects: false } } };
  expect(visualPreviewKey(request)).toBe(visualPreviewKey(changed));
  expect(stableKey(request)).not.toBe(stableKey(changed));
});

it("stops an audition when leaving the panel", async () => {
  const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
  const user = userEvent.setup();
  const view = render(<Panel />);
  await user.click(screen.getByRole("button", { name: "Listen to Quiet morning" }));
  view.unmount();
  expect(pause).toHaveBeenCalledOnce();
});
