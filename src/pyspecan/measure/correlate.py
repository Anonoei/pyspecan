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

def peaks(r: np.ndarray, count: int = 3, start: int | None = None, floor: float = 0.0) -> list[tuple[int, float]]:
    """[(lag, value)] of the `count` highest local maxima past the main lobe over `floor`, highest first. For n samples
    of noise |R| is about 1 / sqrt(n): a floor of a few times that keeps the noise's own ripple out"""
    start = lobe_end(r) if start is None else start
    if len(r) - start < 3:
        return []
    seg = r[start:]
    k = np.flatnonzero((seg[1:-1] > seg[:-2]) & (seg[1:-1] >= seg[2:])) + 1
    k = k[seg[k] > floor]
    k = k[np.argsort(-seg[k])][:count]
    return [(int(start + i), float(seg[i])) for i in k]
