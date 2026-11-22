"""Oscilloscope triggering and decimation, and the gate that picks the frames of a gated spectrum"""
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

def power_db(samples: np.ndarray, smooth: int = 1) -> np.ndarray:
    """Each sample's power in dB full scale (|x|^2 = 1 is 0 dBFS), a moving average over `smooth` samples first"""
    p = np.abs(np.asarray(samples)) ** 2
    if smooth > 1 and len(p) >= smooth:
        c = np.concatenate(([0.0], np.cumsum(p, dtype=np.float64)))
        p = np.concatenate((np.full(smooth - 1, c[smooth] / smooth), (c[smooth:] - c[:-smooth]) / smooth))
    return 10.0 * np.log10(np.maximum(p, 1e-30))

def gate_spans(power: np.ndarray, level: float, delay: int = 0, length: int = 0) -> list[tuple[int, int]]:
    """[(start, stop)) sample spans a gate is open over: each run of `power` at or over `level` opens it `delay` samples
    after the run starts, for `length` samples (0: until the run ends). A run already on at the start of the record has
    no edge to delay from and is used from its start"""
    on = np.asarray(power) >= level
    if not on.any():
        return []
    d = np.diff(on.astype(np.int8))
    starts = np.flatnonzero(d == 1) + 1
    stops = np.flatnonzero(d == -1) + 1
    if on[0]:
        starts = np.concatenate(([0], starts))
    if on[-1]:
        stops = np.concatenate((stops, [len(on)]))
    out = []
    for a, b in zip(starts, stops, strict=True):
        a0 = int(a) + (delay if a > 0 else 0)
        b0 = min(a0 + length, len(on)) if length > 0 else int(b)
        if b0 > a0:
            out.append((a0, b0))
    return out

def frame_starts(spans: list[tuple[int, int]], n: int) -> np.ndarray:
    """Starts of the back to back `n` sample frames that fit inside the spans"""
    starts = [np.arange(a, b - n + 1, n) for a, b in spans if b - a >= n]
    return np.concatenate(starts).astype(np.int64) if starts else np.empty(0, np.int64)

def auto_level(power: np.ndarray) -> float:
    """A gate level between the floor and the peaks: halfway (in dB) from the 10th to the 99th percentile"""
    lo, hi = np.percentile(power, (10, 99))
    return float((lo + hi) / 2)
