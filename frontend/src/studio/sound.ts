import type { SoundSettings } from "./types";

export const DEFAULT_SOUND: SoundSettings = {
  effects: true, effects_volume: .75,
  music: { track: null, asset: null, volume: .25, fade_out: true, loop: true },
};

export function soundSettings(value: SoundSettings | undefined): SoundSettings {
  return { ...DEFAULT_SOUND, ...value, music: { ...DEFAULT_SOUND.music, ...value?.music } };
}
