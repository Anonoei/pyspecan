"""FFT windows and their noise / gain figures"""
from functools import lru_cache

import numpy as np

def _cosine_sum(n: int, coeffs: tuple[float, ...]) -> np.ndarray:
    """Symmetric generalised cosine window (same convention as np.blackman)"""
    if n <= 1:
        return np.ones(max(n, 0))
    x = 2.0 * np.pi * np.arange(n) / (n - 1)
    w = np.zeros(n)
    for k, a in enumerate(coeffs):
        w += (-1)**k * a * np.cos(k * x)
    return w

def flattop(n: int) -> np.ndarray:
    """5-term flat top (SRS), amplitude accurate to ~0.01 dB for any bin offset"""
    return _cosine_sum(n, (0.21557895, 0.41663158, 0.277263158, 0.083578947, 0.006947368))

def blackmanharris(n: int) -> np.ndarray:
    """4-term minimum sidelobe Blackman-Harris"""
    return _cosine_sum(n, (0.35875, 0.48829, 0.14128, 0.01168))

WindowLUT = {
    "rect": np.ones,
    "blackman": np.blackman,
    "hanning": np.hanning,
    "hamming": np.hamming,
    "flattop": flattop,
    "blackmanharris": blackmanharris,
}

def enbw(w: np.ndarray) -> float:
    """Equivalent noise bandwidth in bins: N * sum(w^2) / sum(w)^2"""
    w = np.asarray(w, dtype=float)
    return float(len(w) * np.sum(w**2) / np.sum(w)**2)

def coherent_gain(w: np.ndarray) -> float:
    """sum(w) / N"""
    w = np.asarray(w, dtype=float)
    return float(np.sum(w) / len(w))

@lru_cache(maxsize=32)
def _cached(name: str, n: int) -> np.ndarray:
    w = WindowLUT[name](n)
    w.setflags(write=False)
    return w

def window(name: str, n: int) -> np.ndarray:
    """Cached, read-only window of length n"""
    return _cached(name, int(n))
