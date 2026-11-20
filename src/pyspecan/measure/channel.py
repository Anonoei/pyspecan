"""Channel measurements on a linear power density (power per Hz) and its frequency axis"""
import numpy as np


def _df(freqs: np.ndarray) -> float:
    return float(freqs[1] - freqs[0]) if len(freqs) > 1 else 1.0

def _weights(freqs: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Fraction of each bin [f-df/2, f+df/2] that lies inside [lo, hi]"""
    df = _df(freqs)
    a = np.maximum(freqs - df / 2, lo)
    b = np.minimum(freqs + df / 2, hi)
    return np.clip(b - a, 0.0, None) / df

def band_power(density_lin: np.ndarray, freqs: np.ndarray, lo: float, hi: float) -> float:
    """Power in [lo, hi] Hz: the density integrated over the band (partial edge bins weighted).
    `density_lin` may be (k, n), then k powers are returned"""
    density_lin = np.asarray(density_lin, dtype=float)
    freqs = np.asarray(freqs, dtype=float)
    out = np.sum(density_lin * _weights(freqs, lo, hi), axis=-1) * _df(freqs)
    return float(out) if out.ndim == 0 else out

def acpr(density_lin, freqs, center: float, bw: float, offsets, adj_bw: float | None = None):
    """Main channel power and the power of each +/- offset channel relative to it.

    Returns (main_power, lower_dbc, upper_dbc), the dBc arrays are aligned with `offsets`.
    """
    adj_bw = bw if adj_bw is None else adj_bw
    main = band_power(density_lin, freqs, center - bw / 2, center + bw / 2)
    def rel(c):
        p = band_power(density_lin, freqs, c - adj_bw / 2, c + adj_bw / 2)
        return 10.0 * np.log10(max(p, 1e-30) / max(main, 1e-30))
    offsets = [abs(float(o)) for o in offsets]
    lower = np.array([rel(center - o) for o in offsets])
    upper = np.array([rel(center + o) for o in offsets])
    return main, lower, upper

def obw(density_lin, freqs, lo: float, hi: float, pct: float = 99.0) -> tuple[float, float, float]:
    """Occupied bandwidth: the span containing pct% of the power in [lo, hi], with equal tails.

    Returns (f_low, f_high, total_power).
    """
    density_lin = np.asarray(density_lin, dtype=float)
    freqs = np.asarray(freqs, dtype=float)
    df = _df(freqs)
    p = density_lin * _weights(freqs, lo, hi) * df
    total = float(p.sum())
    if total <= 0 or len(freqs) < 2:
        return lo, hi, total
    cum = np.concatenate(([0.0], np.cumsum(p)))
    edges = np.concatenate((freqs - df / 2, [freqs[-1] + df / 2]))
    tail = (1.0 - pct / 100.0) / 2.0
    f_lo = float(np.interp(tail * total, cum, edges))
    f_hi = float(np.interp((1.0 - tail) * total, cum, edges))
    return f_lo, f_hi, total

def xdb_bw(y_db, freqs, peak_i: int, x: float = 26.0) -> tuple[float, float]:
    """The -x dB bandwidth around bin `peak_i` -> (f_low, f_high), linearly interpolated.
    A side that never falls x dB below the peak ends at the edge of the axis."""
    y_db = np.asarray(y_db, dtype=float)
    freqs = np.asarray(freqs, dtype=float)
    level = y_db[peak_i] - x
    def edge(step):
        i = peak_i
        while 0 <= i + step < len(y_db):
            nxt = i + step
            if y_db[nxt] < level:
                t = (y_db[i] - level) / (y_db[i] - y_db[nxt])
                return float(freqs[i] + t * (freqs[nxt] - freqs[i]))
            i = nxt
        return float(freqs[i])
    return edge(-1), edge(1)
