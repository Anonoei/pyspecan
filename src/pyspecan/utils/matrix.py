"""Persistence histograms: count where a stack of PSDs spends its time, per (level, frequency) pixel"""
from functools import lru_cache

import numpy as np


@lru_cache(maxsize=16)
def _col_map(n: int, x: int):
    """How n PSD bins become x columns, cached because it only depends on the sizes"""
    if x < n: # several bins share a column: its peak
        return "max", (np.arange(x, dtype=np.int64) * n // x)
    pos = np.arange(x, dtype=np.float64) * ((n - 1) / max(x - 1, 1))
    i0 = np.minimum(pos.astype(np.int64), max(n - 2, 0))
    return "lerp", (i0, (pos - i0).astype(np.float32))

def columns(psds: np.ndarray, x: int) -> np.ndarray:
    """(n bins, k frames) -> (x columns, k) with exactly one value per column per frame.

    Mapping bins to columns by position alone makes some columns collect two bins and the
    rest one, which shows up as stripes. So: columns that cover several bins keep their peak,
    and when there are more columns than bins the trace is interpolated between bins.
    """
    n = psds.shape[0]
    if x == n:
        return psds
    kind, arg = _col_map(n, x)
    if kind == "max":
        return np.maximum.reduceat(psds, arg, axis=0)
    i0, w = arg
    w = w[:, None]
    return psds[i0] * (1 - w) + psds[np.minimum(i0 + 1, n - 1)] * w

def _levels(psds: np.ndarray, y: int, yt: float, yb: float) -> np.ndarray:
    """(n, k) histogram row of every PSD point, unclipped, int32"""
    scale = np.float32(y / (yt - yb))
    lvl = np.subtract(psds, np.float32(yb), dtype=np.float32)
    lvl *= scale
    np.floor(lvl, out=lvl)
    np.clip(lvl, -2, y + 1, out=lvl) # keep off scale points off scale, and the cast safe
    return lvl.astype(np.int32)

def dot(x: int, y: int, psds: np.ndarray, yt: float, yb: float) -> np.ndarray:
    """Dot matrix: each frame puts one hit per column, at its level, (y, x) int32.
    psds is (n bins, k frames); level 0 is the bottom row"""
    hist = np.zeros((y, x), dtype=np.int32)
    if not psds.size or yt <= yb:
        return hist
    rows = _levels(columns(psds, x), y, yt, yb)
    cols = np.broadcast_to(np.arange(x, dtype=np.int64)[:, None], rows.shape)
    ok = (rows >= 0) & (rows < y)
    flat = rows[ok].astype(np.int64) * x + cols[ok]
    hist.ravel()[:] = np.bincount(flat, minlength=y * x)
    return hist

def vec(x: int, y: int, psds: np.ndarray, yt: float, yb: float) -> np.ndarray:
    """Vector matrix: each frame is a connected line, so a pixel's count is how many frames drew
    through it, (y, x) int32.

    Consecutive columns are always joined. The join between two columns changes level halfway,
    so each column draws the one contiguous span from the halfway point to its left neighbour,
    through its own level, to the halfway point to its right neighbour, and a frame counts at
    most once per pixel. The spans are added with a difference array (+1 at the top, -1 below
    the bottom) and one cumulative sum, nothing loops over frames.
    """
    if not psds.size or yt <= yb:
        return np.zeros((y, x), dtype=np.int32)
    rows = _levels(columns(psds, x), y, yt, yb)
    mid = (rows[:-1] + rows[1:]) >> 1
    left, right = rows.copy(), rows.copy()
    left[1:] = mid
    right[:-1] = mid
    lo = np.minimum(np.minimum(rows, left), right)
    hi = np.maximum(np.maximum(rows, left), right)
    ok = (hi >= 0) & (lo < y)               # spans that cross the visible levels
    np.clip(lo, 0, y - 1, out=lo)
    np.clip(hi, 0, y - 1, out=hi)
    cols = np.broadcast_to(np.arange(x, dtype=np.int64)[:, None], rows.shape)
    start = lo[ok].astype(np.int64) * x + cols[ok]
    stop = (hi[ok].astype(np.int64) + 1) * x + cols[ok]
    size = (y + 1) * x
    diff = np.bincount(start, minlength=size).astype(np.int32)
    diff -= np.bincount(stop, minlength=size).astype(np.int32)
    diff = diff.reshape(y + 1, x)
    np.cumsum(diff, axis=0, out=diff)
    return diff[:y]

def cvec(x: int, y: int, psds: np.ndarray, yt: float = 0.05, yb: float = 0.05) -> np.ndarray:
    """Vector style matrix, what the persistence plot shows by default"""
    return vec(x, y, psds, yt, yb)
