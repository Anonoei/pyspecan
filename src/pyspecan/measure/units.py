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
    spectra = np.asarray(spectra)
    # the window's power folds into one dB offset, and the math stays in the spectra's precision
    den = fs * np.sum(w**2) if is_density(unit) else np.sum(w)**2
    p = np.abs(spectra)
    np.multiply(p, p, out=p)
    np.maximum(p, FLOOR * den, out=p)
    np.log10(p, out=p)
    p *= 10.0
    db = p
    offset = -10.0 * np.log10(den)
    if unit.startswith("dBm"):
        offset += cal_db - ext_gain_db
    db += p.dtype.type(offset)
    return db
