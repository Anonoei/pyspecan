"""Complementary cumulative distribution of instantaneous power"""
import numpy as np

PERCENTS = (10.0, 1.0, 0.1, 0.01)

class CCDF:
    """Histogram of instantaneous power in absolute dB (|x|^2, clipped to [lo, hi]).
    The mean power is tracked separately, so the curve is reported in dB above the mean."""
    def __init__(self, bins: int = 1000, lo: float = -140.0, hi: float = 20.0):
        self.bins = int(bins)
        self.lo = float(lo)
        self.hi = float(hi)
        self.edges = np.linspace(self.lo, self.hi, self.bins + 1)
        self.reset()

    def reset(self):
        self.hist = np.zeros(self.bins, dtype=np.int64)
        self.total = 0
        self.sum_pow = 0.0
        self.max_pow = 0.0

    def update(self, x: np.ndarray):
        p = np.abs(np.asarray(x)).ravel().astype(float)**2
        if not len(p):
            return
        self.sum_pow += float(p.sum())
        self.max_pow = max(self.max_pow, float(p.max()))
        db = 10.0 * np.log10(np.maximum(p, 1e-30))
        idx = np.clip(((db - self.lo) / (self.hi - self.lo) * self.bins).astype(np.intp), 0, self.bins - 1)
        self.hist += np.bincount(idx, minlength=self.bins)
        self.total += len(p)

    @property
    def avg_db(self) -> float:
        if not self.total:
            return float("nan")
        return 10.0 * np.log10(max(self.sum_pow / self.total, 1e-30))

    def _tail(self) -> np.ndarray:
        """P(power > upper edge of bin j)"""
        return (self.total - np.cumsum(self.hist)) / self.total

    def curve(self) -> tuple[np.ndarray, np.ndarray]:
        """(dB above mean, P(>x)) for every x with a non-zero probability"""
        if not self.total:
            return np.empty(0), np.empty(0)
        prob = self._tail()
        x = self.edges[1:] - self.avg_db
        keep = prob > 0
        return x[keep], prob[keep]

    def stats(self) -> dict:
        """average power (dB), peak (dB), papr (dB) and the dB above mean reached with probability 10, 1, 0.1, 0.01 %"""
        if not self.total:
            return {"avg": float("nan"), "peak": float("nan"), "papr": float("nan"), **{f"p{p:g}": float("nan") for p in PERCENTS}}
        avg = self.avg_db
        peak = 10.0 * np.log10(max(self.max_pow, 1e-30))
        out = {"avg": avg, "peak": peak, "papr": peak - avg}
        prob = self._tail()
        x = self.edges[1:] - avg
        for p in PERCENTS:
            j = int(np.argmax(prob <= p / 100.0))
            out[f"p{p:g}"] = float(x[j]) if prob[j] <= p / 100.0 else float("nan")
        return out
