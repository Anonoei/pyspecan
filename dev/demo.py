"""The synthetic capture the dev tools (screenshots.py, profile_plots.py) run on: the same signals every time, numpy only

a QPSK signal with an echo, an FM carrier, a clean carrier with phase noise, two tones with their third order products,
a bursty signal, a slow chirp, and noise, at 1 MS/s
"""
import numpy as np

FS = 1e6
SECONDS = 2.0

def _shaped(symbols: np.ndarray, sps: int, beta: float) -> np.ndarray:
    """Symbols through a root raised cosine, shaped in frequency"""
    up = np.zeros(len(symbols) * sps, complex)
    up[::sps] = symbols
    f = np.abs(np.fft.fftfreq(len(up))) * sps # in symbol rates
    rc = np.where(f <= (1 - beta) / 2, 1.0, np.where(f <= (1 + beta) / 2, 0.5 * (1 + np.cos(np.pi / beta * (f - (1 - beta) / 2))), 0.0))
    x = np.fft.ifft(np.fft.fft(up) * np.sqrt(rc))
    return x / np.sqrt(np.mean(np.abs(x)**2))

def capture(n: int = int(FS * SECONDS), seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(n) / FS
    tone = lambda f, a: a * np.exp(2j * np.pi * f * t)
    x = np.zeros(n, complex)
    # QPSK, 50 kBd at +150 kHz, through an echo 100 us later (the network analyzer and impulse response show it)
    sps = 20
    q = ((rng.integers(0, 2, n // sps + 1) * 2 - 1) + 1j * (rng.integers(0, 2, n // sps + 1) * 2 - 1)) / np.sqrt(2)
    s = _shaped(q, sps, 0.35)[:n]
    s = s + 0.1 * np.roll(s, 100)
    x += s * np.exp(2j * np.pi * 150e3 * t)
    # an FM carrier at -300 kHz: a 1.5 kHz tone, 6 kHz deviation
    x += 0.5 * np.exp(1j * (2 * np.pi * -300e3 * t + 6e3 / 1.5e3 * np.sin(2 * np.pi * 1.5e3 * t)))
    # a clean carrier at -420 kHz with phase noise (a random walk)
    x += 0.3 * np.exp(1j * (2 * np.pi * -420e3 * t + np.cumsum(rng.standard_normal(n)) * 4e-4))
    # two tones and their third order products (-40 dBc)
    x += tone(-120e3, 0.2) + tone(-100e3, 0.2) + tone(-140e3, 0.002) + tone(-80e3, 0.002)
    # a bursty BPSK signal at +360 kHz, on 40% of the time
    b = _shaped(rng.integers(0, 2, n // 40 + 1) * 2 - 1.0, 40, 0.5)[:n]
    on = ((t * 8) % 1.0) < 0.4
    x += 0.25 * b * on * np.exp(2j * np.pi * 360e3 * t)
    # a slow chirp sweeping -60 kHz .. +60 kHz
    f0, f1 = -60e3, 60e3
    phase = 2 * np.pi * (f0 * t + (f1 - f0) / (2 * SECONDS) * t**2)
    x += 0.03 * np.exp(1j * phase)
    x += 0.01 * (rng.standard_normal(n) + 1j * rng.standard_normal(n))
    return x.astype(np.complex64)

