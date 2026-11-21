"""Turning many points into what a frame can carry: a long trace as a min / max envelope, points as a density image"""
import numpy as np

from ..measure import trigger

COLS = 500 # screen columns: traces longer than 2 * COLS points are drawn as a min / max envelope

def envelope(x: np.ndarray, y: np.ndarray, cols: int = COLS) -> tuple[np.ndarray, np.ndarray]:
    """A long trace as a min / max envelope over `cols` columns, drawn as one line (x, y unchanged when short)"""
    if len(y) <= 2 * cols:
        return x, y
    mn, mx = trigger.envelope(y, cols)
    xs = x[(np.arange(cols) * len(x)) // cols]
    return np.repeat(xs, 2), np.column_stack((mn, mx)).ravel()

def density(y: np.ndarray, x: np.ndarray, rows: int, cols: int, yr: tuple, xr: tuple) -> np.ndarray:
    """(rows, cols) counts of the points (x, y) over the ranges, row 0 at the top (the largest y): np.histogram2d's
    counts by direct integer binning (it binary searches every point, many times slower)"""
    j = np.floor((np.asarray(x, dtype=np.float64) - xr[0]) * (cols / (xr[1] - xr[0]))).astype(np.int64)
    i = np.floor((yr[1] - np.asarray(y, dtype=np.float64)) * (rows / (yr[1] - yr[0]))).astype(np.int64)
    ok = (i >= 0) & (i < rows) & (j >= 0) & (j < cols)
    return np.bincount(i[ok] * cols + j[ok], minlength=rows * cols).reshape(rows, cols).astype(np.float64)

def accumulate(hist: np.ndarray | None, new: np.ndarray, decay: float) -> np.ndarray:
    """A density built up over blocks: the earlier ones fade by `decay` (0 keeps only the newest); a new shape starts over"""
    if hist is None or hist.shape != new.shape:
        return new
    return hist * decay + new

def log_image(hist: np.ndarray) -> np.ndarray:
    """Counts as a uint8 image on a log scale (rare cells still show), the fullest cell 255"""
    top = float(hist.max())
    if top <= 0:
        return np.zeros(hist.shape, dtype=np.uint8)
    return np.rint(np.log1p(hist) * (255.0 / np.log1p(top))).astype(np.uint8)
