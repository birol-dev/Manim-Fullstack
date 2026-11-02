# Original Studio sound pack

All effects and the three original music loops are synthesized by
`studio/audio.py` from oscillators, seeded noise and original note sequences.
No downloaded recordings, samples, soundfonts or third-party compositions are used.
Generated WAVs live in the workspace audio cache, never in the installation.

The generator and its generated audio are distributed under this repository's
MIT license. Users may redistribute the generated audio, including in commercial
videos. Uploaded music remains the uploader's material.

Effects have short click-free envelopes and a -3 dBFS sample peak before the
fader (-5.5 dBFS at default settings). Original 48 kHz stereo music is measured
and normalized to -16 LUFS integrated with the NumPy BS.1770 meter. Music ducks
around effects; the mix has a -1 dBFS sample-peak limiter. This does not claim
certified oversampled true-peak limiting. See SOUND.md for the dB fader mapping.
Bump AUDIO_VERSION after synthesis changes.
