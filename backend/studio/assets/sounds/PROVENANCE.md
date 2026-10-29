# Original Studio sound pack

All effects and the three original music loops are synthesized by
`studio/audio.py` from oscillators, seeded noise and original note sequences.
No downloaded recordings, samples, soundfonts or third-party compositions are used.
Generated WAVs live in the workspace audio cache, never in the installation.

The generator and its generated audio are distributed under this repository's
MIT license. Users may redistribute the generated audio, including in commercial
videos. Uploaded music remains the uploader's material.

Effects have a -16 dBFS sample-peak ceiling, short click-free envelopes and a
default gain below that ceiling. This is **not a measured -16 LUFS claim**:
integrated loudness and sample peak are different quantities, especially for
short effects. Music is staged below effects and ducked around cues; the final
mix is capped at 0.89 full scale. Bump AUDIO_VERSION after synthesis changes.
