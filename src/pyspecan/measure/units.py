"""Spectrum scaling: windowed FFT bins -> calibrated dB"""
import numpy as np

UNITS = ("dB/Hz", "dBFS", "dBm", "dBm/Hz")
FLOOR = 1e-30

def db_to_lin(db):
    return 10.0 ** (np.asarray(db, dtype=float) / 10.0)

def lin_to_db(lin):
    return 10.0 * np.log10(np.maximum(lin, FLOOR))

def is_density(unit: str) -> bool:
    return unit in ("dB/Hz", "dBm/Hz")

def rbw(fs: float, nfft: int, w: np.ndarray) -> float:
    """Resolution bandwidth (Hz) = ENBW * fs / nfft"""
    from .windows import enbw
    return enbw(w) * fs / nfft

def scale(spectra: np.ndarray, fs: float, w: np.ndarray, unit: str = "dB/Hz",
          cal_db: float = 0.0, ext_gain_db: float = 0.0) -> np.ndarray:
    """(k, nfft) complex spectra of x*w -> dB in `unit`

    Density units divide by fs*sum(w^2), so white noise of variance s2 reads 10log10(s2/fs)
    for any window. Power units divide by sum(w)^2, so a full scale complex tone reads 0 dBFS.
    dBm* units add `cal_db` (the dBm reading at 0 dBFS) and subtract `ext_gain_db`.
    """
    if unit not in UNITS:
        raise ValueError(f"unknown unit {unit!r}")
    w = np.asarray(w, dtype=float)
    p = np.abs(spectra)**2
    if is_density(unit):
        p = p / (fs * np.sum(w**2))
    else:
        p = p / np.sum(w)**2
    db = lin_to_db(p)
    if unit.startswith("dBm"):
        db = db + (cal_db - ext_gain_db)
    return db
