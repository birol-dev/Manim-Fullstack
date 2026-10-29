import type { SoundSettings } from "./types";

export const DEFAULT_SOUND: SoundSettings = {
  effects: true, effects_volume: .75,
  music: { track: null, asset: null, volume: 1, fade_out: true, loop: true },
};

/** Matches the backend dB fader: 25/50/75/100% = -22.5/-10/-2.5/0 dB. */
export function volumeGain(value: number): number {
  return value > 0 ? 10 ** (-40 * (1 - value) ** 2 / 20) : 0;
}

export function soundSettings(value: SoundSettings | undefined): SoundSettings {
  return { ...DEFAULT_SOUND, ...value, music: { ...DEFAULT_SOUND.music, ...value?.music } };
}
