"""Peak search"""
import numpy as np

def _walk_min(y: np.ndarray, i: int, step: int) -> float:
    """Lowest value walking from i in direction `step` until a value higher than y[i] (or the edge)"""
    lvl = y[i]
    lo = lvl
    pos = i + step
    chunk = 64
    while 0 <= pos < len(y):
        if step > 0:
            seg = y[pos:pos + chunk]
        else:
            seg = y[max(pos - chunk + 1, 0):pos + 1][::-1]
        hit = np.flatnonzero(seg > lvl)
        if len(hit):
            if hit[0]:
                lo = min(lo, float(seg[:hit[0]].min()))
            break
        lo = min(lo, float(seg.min()))
        pos += step * len(seg)
        chunk *= 2
    return lo

def _prominence(y: np.ndarray, i: int) -> float:
    """Height of y[i] above the higher of the left / right bases"""
    return float(y[i] - max(_walk_min(y, i, -1), _walk_min(y, i, 1)))

def find_peaks(y: np.ndarray, n: int, threshold: float | None = None, excursion_db: float = 6.0) -> np.ndarray:
    """Indices of the n highest local maxima of `y` that rise >= excursion_db above their surroundings
    (and are >= threshold when given), sorted by level, highest first"""
    y = np.asarray(y, dtype=float)
    if len(y) < 3 or n <= 0:
        return np.empty(0, dtype=np.intp)
    mid = y[1:-1]
    cand = np.flatnonzero((mid > y[:-2]) & (mid >= y[2:])) + 1
    if threshold is not None:
        cand = cand[y[cand] >= threshold]
    cand = cand[np.argsort(-y[cand], kind="stable")]
    found = []
    for i in cand:
        if _prominence(y, int(i)) >= excursion_db:
            found.append(int(i))
            if len(found) >= n:
                break
    return np.array(found, dtype=np.intp)

def interp(y: np.ndarray, i: int) -> tuple[float, float]:
    """Parabolic refinement around bin i -> (fractional index, level)"""
    if i <= 0 or i >= len(y) - 1:
        return float(i), float(y[i])
    a, b, c = float(y[i-1]), float(y[i]), float(y[i+1])
    den = a - 2*b + c
    if den == 0:
        return float(i), b
    d = 0.5 * (a - c) / den
    return i + d, b - 0.25 * (a - c) * d
