"""Oscilloscope triggering and decimation"""
import numpy as np

SOURCES = ("I", "Q", "Mag")
EDGES = ("rising", "falling")

def signal(samples: np.ndarray, source: str = "I") -> np.ndarray:
    """The real signal a trigger watches"""
    if source == "I":
        return samples.real
    if source == "Q":
        return samples.imag
    if source == "Mag":
        return np.abs(samples)
    raise ValueError(f"unknown trigger source {source!r}, use {', '.join(SOURCES)}")

def find(sig: np.ndarray, level: float = 0.0, edge: str = "rising", spacing: float = 0.0) -> np.ndarray:
    """Fractional sample positions where `sig` crosses `level` on `edge`, oldest first

    A crossing between samples i-1 and i is placed by linear interpolation, so a trace drawn
    relative to it does not jitter by a sample. Triggers closer than `spacing` samples to the
    previous kept one are skipped (a scope re-arms only after its record and holdoff).
    """
    sig = np.asarray(sig, dtype=np.float64)
    if len(sig) < 2:
        return np.empty(0)
    a, b = sig[:-1], sig[1:]
    if edge == "rising":
        idx = np.flatnonzero((a < level) & (b >= level))
    elif edge == "falling":
        idx = np.flatnonzero((a > level) & (b <= level))
    else:
        raise ValueError(f"unknown trigger edge {edge!r}, use {', '.join(EDGES)}")
    pos = idx + (level - a[idx]) / (b[idx] - a[idx]) # b != a: they lie on opposite sides of level
    if spacing <= 1 or len(pos) < 2:
        return pos
    kept = []
    i = 0
    while i < len(pos):
        kept.append(pos[i])
        i = int(np.searchsorted(pos, pos[i] + spacing, side="left"))
    return np.asarray(kept)

def envelope(sig: np.ndarray, bins: int) -> tuple[np.ndarray, np.ndarray]:
    """(min, max) of `sig` over `bins` equal spans, a spike shorter than a span is kept

    With no more samples than bins, the samples themselves are both min and max.
    """
    sig = np.asarray(sig)
    n = len(sig)
    if n <= bins:
        return sig, sig
    edges = (np.arange(bins) * n) // bins
    return np.minimum.reduceat(sig, edges), np.maximum.reduceat(sig, edges)
