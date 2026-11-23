"""Autocorrelation: how much a signal resembles itself a lag later"""
import numpy as np


def autocorr(x: np.ndarray, max_lag: int, remove_dc: bool = True) -> np.ndarray:
    """|R(L)| / R(0) for L in [0, max_lag]: |sum x(n+L) x*(n)| over the record's energy (by FFT, zero padded so the
    lags do not wrap). A lag near the record's length sums fewer products, so reads low"""
    x = np.asarray(x, dtype=np.complex128)
    if remove_dc and len(x):
        x = x - x.mean()
    n = len(x)
    max_lag = min(max_lag, n - 1)
    if max_lag < 0:
        return np.zeros(0)
    nfft = 1 << int(np.ceil(np.log2(max(2, n + max_lag + 1))))
    X = np.fft.fft(x, nfft)
    r = np.fft.ifft(np.abs(X) ** 2)[:max_lag + 1]
    r0 = float(np.real(r[0]))
    return np.abs(r) / r0 if r0 > 0 else np.zeros(max_lag + 1)

def lobe_end(r: np.ndarray) -> int:
    """The lag where the main lobe (around lag 0) ends: the first local minimum, or the first lag under half"""
    if len(r) < 3:
        return len(r)
    d = np.diff(r)
    rise = np.flatnonzero(d > 0)
    half = np.flatnonzero(r < 0.5)
    ends = [int(rise[0]) if len(rise) else len(r), int(half[0]) if len(half) else len(r)]
    return min(ends)

def peaks(r: np.ndarray, count: int = 3, start: int | None = None, floor: float = 0.0,
          stand: float = 2.0) -> list[tuple[int, float]]:
    """[(lag, value)] of the `count` highest local maxima past the main lobe that stand out from their surroundings,
    highest first: each over `floor` and at least `stand` times the mean of |R| around it (a quarter of its lag each
    side). A repetition is a spike over its surroundings; narrow band signals' |R| ripples slowly near lag 0 (their
    beats), higher than a repetition but not standing out. Of a repetition's multiples the first is the highest (fewer
    products sum at a longer lag). For n samples of noise |R| is about 1 / sqrt(n): a floor of a few times
    that keeps the noise's own ripple out"""
    start = lobe_end(r) if start is None else start
    if len(r) - start < 3:
        return []
    seg = r[start:]
    k = np.flatnonzero((seg[1:-1] > seg[:-2]) & (seg[1:-1] >= seg[2:])) + 1
    lag = start + k[seg[k] > floor]
    if not len(lag):
        return []
    c = np.concatenate(([0.0], np.cumsum(r)))
    w = np.maximum(4, lag // 4)
    lo, hi = np.maximum(start, lag - w), np.minimum(len(r), lag + w + 1)
    around = (c[hi] - c[lo]) / (hi - lo) # the mean around each (one pass, however many peaks)
    keep = lag[r[lag] >= stand * np.maximum(around, 1e-12)]
    keep = keep[np.argsort(-r[keep])][:count]
    return [(int(i), float(r[i])) for i in keep]
