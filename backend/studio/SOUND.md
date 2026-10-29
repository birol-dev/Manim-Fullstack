# Studio sound

Sound is a shared `RenderSettings.sound` block. Old projects get restrained
effects by default and no music. Uploads and bundled tracks are mutually exclusive.
Levels are 0–1; music defaults to 1 (100%) and effects to .75. Fade-out and repeat default on. Energy changes effect gain only,
never the scene clock or the music tempo.

## Original material and levels

`audio.py` generates eight effects and three original melodic loops from NumPy
oscillators and seeded noise. Audition WAVs are generated atomically in
`workspace/studio/audio-cache`; nothing writes to the installed backend.
See `assets/sounds/PROVENANCE.md` for redistribution and level details.
Music sources are normalized to **-16 LUFS integrated** before the volume fader.
`loudness.py` implements the 48 kHz stereo K-weighting and absolute/relative gates
from [ITU-R BS.1770-5](https://www.itu.int/rec/R-REC-BS.1770/en) with NumPy.
Its measurements are cross-checked against FFmpeg's independent `ebur128` meter.
The fader applies a dB curve: 25/50/75/100% are -22.5/-10/-2.5/0 dB; 0 is silence.
New music defaults to 100%, the mastered listening level. Saved explicit values
are retained, so an existing project's 25% setting should be raised if desired.
The same curve applies to auditions and preview playback volume.

Effects are generated at -3 dBFS peak, yielding -5.5 dBFS at the default 75%
(normal energy). Music ducks by up to 65% around cues. A stereo-linked peak
limiter has a 5 ms lookahead within chunks, 80 ms release carried across chunks,
and a final **-1 dBFS sample-peak ceiling**. This is not a certified dBTP limiter;
lossy encoders can change sample peaks. Unusually transient sources may fall
below the loudness target when the peak ceiling takes priority.

Uploads accept MP3, M4A/AAC, WAV and OGG, at most 50 MB and 10 minutes.
The mix, generators, uploads and export audio streams are **48 kHz stereo**.
Mono uploads are duplicated to stereo; stereo sources retain both channels and
treble above 12 kHz. Original loops have gentle panning, with no downloaded audio.
New uploads are stored as content-addressed **16-bit lossless FLAC**, capped at
64 MB after preparation, avoiding a 110 MB decoded ten-minute WAV on disk.
If lossless compression cannot meet that cap, choose a shorter source and loop it.
The source upload cap remains 50 MB / ten minutes. Preparation currently holds
decoded upload PCM in memory (about 220 MiB plus a normalization working copy
and codec buffers at the maximum duration); normalization/meter temporaries are chunked.
Old 24 kHz mono WAV assets remain valid and are upmixed, resampled and normalized
when read; their discarded treble/stereo cannot be recovered without re-uploading.
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
muted initially; the always-visible Sound off/on button below the artwork remembers
the choice in session storage. Standalone row audition buttons play/stop on a user
gesture; there is no autoplaying audition. Browsers can still block audible autoplay
after a render; the playback Play button resumes it. Listen to the
finish sample to hear a long timer's chime without waiting for its ending.

## Writer compatibility

`audio_render.py` wraps the scene's writer `finish` method, after normal Manim
video assembly. It copies video packets and encodes only the PCM mix: MP4/AAC,
WebM/Opus, MOV/PCM, all stereo 48 kHz. AAC uses 192 kbps and Opus 128 kbps.
This leaves the export queue implementation untouched, runs
before the process returns, and preserves alpha/video encoding.

Manim 0.18.1's native sound writer requires CLI FFmpeg and hard-codes AAC.
Studio avoids that sound path. Its existing CLI media tools are a compatibility
fallback when PyAV is absent. Modern desktop runtimes use PyAV for both upload
decoding and muxing, without spawning FFmpeg/ffprobe. No new package is required.

The desktop smoke now verifies MP4/AAC, 48 kHz stereo and nonzero decoded audio. Its optional
`--audio-formats` probe additionally checks WebM/Opus, MOV/PCM and silent GIF.
Run it against a freshly assembled package, not an older backend snapshot.

## Cache contract: no gallery rebake

Visual preview hashes exclude `sound` entirely. `storage.visual_source` uses the
Python syntax tree to omit only known sound imports/fields, the cue helper and
branches consisting entirely of cues or writer installation. It preserves all
other source bytes, including visual statements, waits and timing. Calls with
side effects in a cue argument or loop/branch condition are retained too.
This preserves exact pre-sound hashes without source comment markers or a rebake,
including CRLF/LF portability. Runtime fingerprints retain every
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
`SoundPanel.test.tsx`, `MotionPreview.test.tsx` and `Editor.history.test.tsx`.
The form uses Content / Look / Sound tabs, with existing Radix keyboard behaviour.
Music cards use radio semantics and arrow/Home/End navigation; sliders have a
44 px hit area, themed fill/thumb/focus and spoken percentage values.
Use `NODE_ENV=test`.
No production build or poster/peek bake is part of this feature's validation.
