"""Trace detectors: map nfft bins onto fewer display points"""
import numpy as np

MODES = ("peak", "sample", "rms", "neg")

def reduce(y: np.ndarray, points: int, mode: str = "peak") -> tuple[np.ndarray, np.ndarray]:
    """Reduce the last axis of dB values `y` to `points` bins (0 or >= len: unchanged).

    Returns (x, y) where x is the bin index (float) at the center of each group.
    """
    if mode not in MODES:
        raise ValueError(f"unknown detector {mode!r}")
    y = np.asarray(y)
    n = y.shape[-1]
    if points <= 0 or points >= n:
        return np.arange(n, dtype=float), y
    edges = np.linspace(0, n, points + 1).astype(np.intp)
    starts = edges[:-1]
    x = (edges[:-1] + edges[1:] - 1) / 2.0
    if mode == "peak":
        out = np.maximum.reduceat(y, starts, axis=-1)
    elif mode == "neg":
        out = np.minimum.reduceat(y, starts, axis=-1)
    elif mode == "sample":
        out = y[..., (edges[:-1] + edges[1:] - 1) // 2]
    else:
        lin = 10.0 ** (y / 10.0)
        out = 10.0 * np.log10(np.add.reduceat(lin, starts, axis=-1) / np.diff(edges))
    return x, out
