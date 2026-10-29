# Studio sound

Sound is a shared `RenderSettings.sound` block. Old projects get restrained
effects by default and no music. Uploads and bundled tracks are mutually exclusive.
Levels are 0–1; fade-out and repeat default on. Energy changes effect gain only,
never the scene clock or the music tempo.

## Original material and levels

`audio.py` generates eight effects and three original melodic loops from NumPy
oscillators and seeded noise. Audition WAVs are generated atomically in
`workspace/studio/audio-cache`; nothing writes to the installed backend.
See `assets/sounds/PROVENANCE.md` for redistribution and level details.
Effects have a -16 dBFS sample-peak ceiling, **not a measured LUFS target**.
Music has fixed headroom below effects and smooth ducking around each cue.
The mixer processes bounded chunks, with a final 0.89 full-scale ceiling.

Uploads accept MP3, M4A/AAC, WAV and OGG, at most 50 MB and 10 minutes.
They are decoded, normalized and stored as content-addressed mono 24 kHz WAVs.
An hour-long video can repeat a short source without allocating an hour of PCM.
`music.loop=false` instead leaves silence after the source ends. Music fades over
the last 1.5 seconds (or half of a shorter video) and is trimmed to actual encoded
video duration, including template introductions and finish cards.

## Template events

Use `self.cue(name, offset=0)` in scene code; it records an event and never waits,
changes a mobject, or calls Manim's `add_sound` with a path.

* Countdown ring/bar: final five seconds. Big numbers: final three. One finish
  chime at the finish-card entrance. There is no ticking throughout a long timer.
* Quiz: final three thinking seconds, one correct-answer chime at reveal.
* Celebration: one sparkle (or a pop without confetti) at the opening landing.
* Announcement and quote: one soft whoosh at the opening, no sound per word.
* Year in review: one opening pop and one soft tick after each number settles.
* No cues were added to the separately owned steps template; shared music works.

Poster/storyboard passes, timing-only passes, PNG/GIF and gallery peeks stay
silent and never synthesize/mix audio. Motion previews contain the mix for the
first 20 seconds; a long timer's finish is outside that preview. Playback starts
muted; Unmute and standalone sample buttons require user gestures. Listen to the
finish sample to hear a long timer's chime without waiting for its ending.

## Writer compatibility

`audio_render.py` wraps the scene's writer `finish` method, after normal Manim
video assembly. It copies video packets and encodes only the PCM mix: MP4/AAC,
WebM/Opus, MOV/PCM. This leaves the export queue implementation untouched, runs
before the process returns, and preserves alpha/video encoding.

Manim 0.18.1's native sound writer requires CLI FFmpeg and hard-codes AAC.
Studio avoids that sound path. Its existing CLI media tools are a compatibility
fallback when PyAV is absent. Modern desktop runtimes use PyAV for both upload
decoding and muxing, without spawning FFmpeg/ffprobe. No new package is required.

The desktop smoke now verifies MP4/AAC and nonzero decoded audio. Its optional
`--audio-formats` probe additionally checks WebM/Opus, MOV/PCM and silent GIF.
Run it against a freshly assembled package, not an older backend snapshot.

## Cache contract: no gallery rebake

Visual preview hashes exclude `sound` entirely. Source hashes for shipped
artwork strip only explicitly marked `# studio-audio` lines or
`# studio-audio-begin`/`# studio-audio-end` additions. This preserves the exact
pre-sound hashes of schema, kit and scene files, including CRLF/LF portability.
**Only audio imports/setup/cues may use these markers. Never mark visual code,
layout changes, waits or animation timing.** Runtime fingerprints retain every
source byte, so workers still reload after an audio-only edit. Motion cache keys
also include sound settings, normalized music file stamps and sound source hashes.

Frontend still/storyboard scheduling excludes sound too; editor history and
autosave retain the full settings. Audio changes invalidate motion playback.
Freshness tests prove all existing preset posters and peeks remain current.

## Validation

`tests/test_studio_sound.py` covers deterministic levels, mixing/loop/fade,
validation, real template event times, MCP/HTTP upload parity, cache separation,
and tiny actual writer outputs in all four containers. Set
`STUDIO_AUDIO_REAL_TESTS=1` to additionally exercise the full export queue with
MP4/AAC and silent GIF. Use the repository's requested pytest basetemp and
`-p no:cacheprovider`; the Windows sandbox may need its normal mkdir-mode shim.

Frontend controls and muted/unmute playback are covered by
`SoundPanel.test.tsx` and `MotionPreview.test.tsx`. Use `NODE_ENV=test`.
No production build or poster/peek bake is part of this feature's validation.
