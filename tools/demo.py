"""The synthetic captures the dev tools (screenshots.py, benchmark.py) run on: the same signals every time, numpy only

`capture`: a QPSK signal with an echo, an FM carrier, a clean carrier with phase noise, two tones with their third order
products, a bursty signal, a slow chirp, and noise, at 1 MS/s.
`structured`: signals cut in time, for the plots that find how (gated PSD, Waveform ID, Bursts, Hopping, Frame Raster):
TDMA bursts sharing a preamble, a frequency hopping FSK, and a QPSK carrier framed by a unique word, at 1 MS/s.
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



def structured(n: int = int(FS * SECONDS), seed: int = 2) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(n) / FS
    qpsk = lambda k: np.exp(1j * (np.pi / 4 + np.pi / 2 * rng.integers(0, 4, k)))
    x = np.zeros(n, complex)
    # TDMA at -250 kHz: QPSK bursts at 100 kBd (348 symbols: a shared 48 symbol preamble, then data), one every 10 ms,
    # each with a carrier phase and a small offset of its own (another transmitter)
    sps, period = 10, 10_000
    preamble = qpsk(48)
    for start in range(200, n - 3600, period):
        b = _shaped(np.concatenate((preamble, qpsk(300))), sps, 0.35)
        k = np.arange(len(b))
        x[start:start + len(b)] += 1.3 * b * np.exp(1j * (rng.uniform(0, 2 * np.pi) + 2 * np.pi * rng.uniform(-300, 300) / FS * k))
    x *= np.exp(2j * np.pi * -250e3 * t)
    # a hopper around 0 Hz: 2-FSK (constant envelope, as most hoppers) at 2.5 kBd, +-1.25 kHz, 2 ms on each of 8
    # channels 30 kHz apart
    dwell = 2000
    chans = (np.arange(8) - 3.5) * 30e3
    f = np.repeat(rng.choice(chans, n // dwell + 1), dwell)[:n]
    f += np.repeat(rng.choice((-1.25e3, 1.25e3), n // 400 + 1), 400)[:n]
    x += np.exp(2j * np.pi * np.cumsum(f) / FS)
    # a framed QPSK carrier at +300 kHz: 50 kBd, a 24 symbol unique word every 200 symbols
    uw = qpsk(24)
    frames = np.concatenate([np.concatenate((uw, qpsk(176))) for _ in range(n // (20 * 200) + 1)])
    x += 0.3 * _shaped(frames, 20, 0.35)[:n] * np.exp(2j * np.pi * 300e3 * t)
    x += 0.01 * (rng.standard_normal(n) + 1j * rng.standard_normal(n))
    return x.astype(np.complex64)
