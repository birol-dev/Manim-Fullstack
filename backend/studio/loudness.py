"""48 kHz stereo BS.1770 loudness and sample-peak control, using NumPy only.

K-weighting coefficients and 400 ms / 75% overlap gating follow ITU-R BS.1770-5
tables 1–2 and Annex 1. FFT overlap-save evaluates the two IIR stages with a
4096-sample history (the remaining impulse response is below float32 precision).
This is a sample-peak limiter, not a certified oversampled true-peak meter.
"""
from functools import lru_cache
import math

from .sound import SAMPLE_RATE

TARGET_LUFS = -16.0
PEAK_CEILING = 10 ** (-1 / 20)


def volume_gain(value):
    """0 is silence; 25/50/75/100% are -22.5/-10/-2.5/0 dB."""
    return 10 ** (-40 * (1 - value) ** 2 / 20) if value > 0 else 0.0


@lru_cache(maxsize=1)
def _weighting():
    import numpy as np
    size = 131072
    z = np.exp(-2j * np.pi * np.arange(size // 2 + 1) / size)
    shelf = (1.53512485958697 - 2.69169618940638*z + 1.19839281085285*z*z) / (1 - 1.69065929318241*z + .73248077421585*z*z)
    highpass = (1 - 2*z + z*z) / (1 - 1.99004745483398*z + .99007225036621*z*z)
    return shelf * highpass


def integrated_loudness(samples):
    """Integrated LUFS of an (n, 2) array, with absolute and relative gating."""
    import numpy as np
    hop, history, size = round(.1 * SAMPLE_RATE), 4096, 131072
    values = np.asarray(samples)
    if values.ndim != 2 or values.shape[1] != 2:
        raise ValueError("The loudness meter expects 48 kHz stereo.")
    if not len(values):
        return -math.inf
    # Retain only 100 ms energy bins, not a second full-length filtered song.
    energies = []
    past = np.zeros((history, 2))
    carry = np.empty(0)
    for start in range(0, len(values), 65536):
        chunk = values[start:start + 65536]
        joined = np.concatenate((past, chunk))
        weighted = np.fft.irfft(np.fft.rfft(joined, n=size, axis=0) * _weighting()[:, None], n=size, axis=0)[history:history + len(chunk)]
        power = np.concatenate((carry, np.sum(weighted * weighted, axis=1)))
        count = len(power) // hop
        energies.extend(power[:count * hop].reshape(count, hop).mean(axis=1))
        carry = power[count * hop:]
        past = joined[-history:]
    if len(energies) < 4:
        # Short effects/uploads use a zero-padded minimum 400 ms measurement.
        energies.extend([float(carry.sum() / hop)] if len(carry) else [])
        energies.extend([0.] * (4 - len(energies)))
    bins = np.asarray(energies)
    powers = np.convolve(bins, np.ones(4) / 4, mode="valid")
    powers = powers[powers > 10 ** ((-70 + .691) / 10)]
    if not len(powers):
        return -math.inf
    powers = powers[powers >= powers.mean() / 10]
    return -.691 + 10 * math.log10(float(powers.mean()))


def limit_peak(samples, *, initial_gain=1., return_gain=False):
    """Stereo-linked 5 ms lookahead, 80 ms release; preserves stereo balance."""
    import numpy as np
    values = np.asarray(samples, dtype=np.float32)
    if not len(values):
        return (values.copy(), initial_gain) if return_gain else values.copy()
    # 1 ms gain bins reduce Python work to 1000 steps/s. Look ahead five bins;
    # carry release gain across mixer chunks so codec frame sizes don't pump.
    step = 48
    peak = np.max(np.abs(values), axis=1)
    padded = np.pad(peak, (0, (-len(peak)) % step))
    peaks = padded.reshape(-1, step).max(axis=1)
    desired = np.minimum(1, PEAK_CEILING / np.maximum(peaks, 1e-12))
    original = desired.copy()
    for look in range(1, 6):
        desired[:-look] = np.minimum(desired[:-look], original[look:])
    gain = np.empty(len(desired))
    previous = initial_gain
    release = math.exp(-.001 / .08)
    for i, target in enumerate(desired):
        previous = min(float(target), 1 - (1 - previous) * release)
        gain[i] = previous
    envelope = np.interp(np.arange(len(values)), (np.arange(len(gain)) + 1) * step, gain)
    result = values * envelope[:, None]
    # Stereo-linked safety catch at a chunk boundary or a one-sample transient.
    safety = np.minimum(1, PEAK_CEILING / np.maximum(np.max(np.abs(result), axis=1), 1e-12))
    result = (result * safety[:, None]).astype(np.float32)
    return (result, float(envelope[-1])) if return_gain else result


def normalize_loudness(samples, target=TARGET_LUFS):
    """Normalize sources before the fader; limit rare peaks, then remeasure."""
    import numpy as np
    level = integrated_loudness(samples)
    if not math.isfinite(level):
        return np.asarray(samples, dtype=np.float32)
    result = np.array(samples, dtype=np.float32, copy=True)
    for _ in range(3):
        gain = 10 ** ((target - level) / 20)
        previous = 1.
        for start in range(0, len(result), 65536):
            limited, previous = limit_peak(result[start:start + 65536] * gain, initial_gain=previous, return_gain=True)
            result[start:start + 65536] = limited
        level = integrated_loudness(result)
        if abs(level - target) < .05:
            break
    return result
