"""What the DSP plots share: their base class (the selection, its lock, why there is none), the symbols' errors,
the matched filter's waveform, the ideal waveform of the decided symbols and the link's response from it"""
import numpy as np

from ..base import Plot
from ..frame import (
    Axis,
    Frame,
)
from ..freq import fmt_hz
from ..settings import Setting
from .analyzer import SPAN, Lock, NoLock, Selection, analyzer

SETTING_DECAY = Setting("decay", "Decay", "number", default=0.6, min=0.0, max=1.0, step=0.05, group="Display",
                        help="how much of the earlier blocks stays each refresh, 0 shows only the latest")


class DSPPlot(Plot):
    """A plot of the selected signal's symbols: finds the selection and its lock, says why when there is none"""
    SETTINGS: tuple = ()

    def reset(self):
        self.sel_key = None # the selection / lock the accumulated state belongs to

    def analyse(self) -> tuple[Selection | None, Lock | None, str]:
        """(selection, lock, why there is no lock)"""
        if not len(self.source.samples):
            return None, None, "no samples"
        an = analyzer(self.source)
        sel = an.selection(self.dsp_freq, self.dsp_bw) # type: ignore
        if sel is None:
            return None, None, "no signal found"
        try:
            lk = an.lock(sel, self.dsp_mod, self.dsp_baud) # type: ignore
        except NoLock as e: # nothing that looks like symbols, with why
            return sel, None, str(e)
        if lk is None:
            return sel, None, "too few samples"
        key = (sel.key, lk.mod, round(lk.baud), lk.Fs)
        if key != self.sel_key:
            self.sel_key = key
            self.changed_lock()
        return sel, lk, ""

    def changed_lock(self):
        """The selection or what was locked changed: drop accumulated state"""

    @staticmethod
    def sel_readout(sel: Selection | None) -> list[tuple[str, str]]:
        if sel is None:
            return []
        return [("Signal", f"{fmt_hz(sel.freq)}, {fmt_hz(sel.width)}" + (" (auto)" if sel.auto else ""))]

    @staticmethod
    def lock_readout(lk: Lock) -> list[tuple[str, str]]:
        return [("Mod", lk.mod), ("Baud", fmt_hz(lk.baud).replace("Hz", "Bd")), ("Roll-off", f"{lk.beta:g}"),
                ("Es/N0", f"{lk.esn0:.1f} dB"), ("EVM", f"{lk.evm:.1f}%"), ("CFO", fmt_hz(lk.cfo))]

    def empty(self, axes: list[Axis], sel, why: str) -> Frame:
        return Frame(axes, title=self.TITLE, readout=[*self.sel_readout(sel), ("Lock", why)])


def error_summary(lk: Lock) -> list[tuple[str, str]]:
    """What a VSA's error summary shows (rpps' Lock.summary()): peak EVM (and where), MER, magnitude / phase error, IQ
    offset, and for a two dimensional constellation gain imbalance and quadrature error"""
    s = lk.rpps.summary() # type: ignore
    out = [("EVM pk", f"{s.evm_peak_pct:.1f}% (symbol {s.evm_peak_at} of {s.n})"), ("MER", f"{s.mer_db:.1f} dB"),
           ("Mag err", f"{s.mag_err_rms_pct:.2f}% rms"), ("Phase err", f"{s.phase_err_rms_deg:.2f}° rms"),
           ("IQ offset", f"{s.iq_offset_db:.1f} dBc")]
    if s.gain_imbalance_db is not None:
        out.append(("Gain imb", f"{s.gain_imbalance_db:+.2f} dB"))
    if s.quad_error_deg is not None:
        out.append(("Quad err", f"{s.quad_error_deg:+.2f}°"))
    out.append(("Symbols", str(s.n)))
    return out


def welch(x: np.ndarray, nfft: int) -> np.ndarray:
    """Mean |X|^2 of hann windowed segments overlapping by half (fftshifted)"""
    win = np.hanning(nfft)
    starts = np.arange(0, len(x) - nfft + 1, nfft // 2)
    if not len(starts):
        return np.zeros(nfft)
    X = np.fft.fftshift(np.fft.fft(x[starts[:, None] + np.arange(nfft)] * win, axis=1), axes=1)
    return np.mean(np.abs(X)**2, axis=0)


def eye_points(lk: Lock, cols: int = 128) -> tuple[np.ndarray, np.ndarray]:
    """(position in [0, 2) symbols, matched filter output) of the selection's waveform, interpolated finer than `cols`
    columns across two symbols (sample spacing would leave stripes). The symbol instants are at 1 (and 0 / 2): the eye
    opens in the middle"""
    t, z = matched(lk, max(1, int(np.ceil(1.5 * cols / (2 * lk.sps)))))
    return (t + 1.0) % 2.0, z


def matched(lk: Lock, up: int) -> tuple[np.ndarray, np.ndarray]:
    """(time in symbols from the first instant, matched filter output) of the selection's waveform, `up` times finer
    than its samples: unit rms at the symbol instants, the carrier offset and phase taken out. rpps' Lock.matched gives
    the same exactly, but evaluates the filter at every point: ~20x the cost at an eye diagram's density"""
    from rpps.signal.filters import rrc_pulse
    xr = lk.rpps.derotated() # type: ignore
    L = int(np.ceil(SPAN * lk.sps))
    h = rrc_pulse(np.arange(-L, L + 1) / lk.sps, lk.beta)
    h = h / np.sqrt(np.sum(h**2))
    z = np.convolve(xr, h, "same")[L:-L] # unit rms at the symbol instants (the lock's gain is in xr already)
    n = len(z)
    if n < 16:
        return np.zeros(0), np.zeros(0, complex)
    Z = np.fft.fft(z)
    pad = np.zeros(n * up, complex)
    half = n // 2
    pad[:half], pad[-(n - half):] = Z[:half], Z[half:]
    zu = np.fft.ifft(pad) * up
    t = (L + np.arange(n * up) / up - lk.centres[0]) / lk.sps # symbols from the first instant
    edge = up * int(np.ceil(lk.sps)) # the interpolation wraps around at the ends
    return t[edge:-edge], zu[edge:-edge]


def pair(lk: Lock) -> tuple[np.ndarray, np.ndarray]:
    """(received, ideal) waveforms without their ends, where the ideal lacks the symbols outside the record"""
    cut = int(np.ceil(2 * SPAN * lk.sps))
    x, r = lk.rpps.derotated(), lk.rpps.reference() # type: ignore
    return (x[cut:-cut], r[cut:-cut]) if len(x) > 4 * cut else (x, r)


def cross_spectra(x: np.ndarray, r: np.ndarray, nfft: int) -> tuple[np.ndarray, np.ndarray]:
    """Welch sums of X R* and |R|^2 (fftshifted), hann windows overlapping by half"""
    win = np.hanning(nfft)
    hop = nfft // 2
    starts = np.arange(0, len(x) - nfft + 1, hop)
    if not len(starts):
        return np.zeros(nfft, complex), np.zeros(nfft)
    seg = lambda a: np.fft.fftshift(np.fft.fft(a[starts[:, None] + np.arange(nfft)] * win, axis=1), axes=1)
    X, R = seg(x), seg(r)
    return np.sum(X * np.conj(R), axis=0), np.sum(np.abs(R)**2, axis=0)


class ResponseMixin:
    """The link's frequency response H = Sxr / Srr, the received over the ideal waveform, averaged over blocks"""
    def changed_lock(self):
        self.sxr = self.srr = None

    def accumulate(self, lk: Lock) -> tuple[np.ndarray, np.ndarray]:
        """(f around the signal's center, mask of the bins inside the signal) after this block; sxr / srr updated"""
        nfft = int(2 ** np.ceil(np.log2(max(16, self.resolution * lk.sps)))) # type: ignore
        sxr, srr = cross_spectra(*pair(lk), nfft)
        if self.sxr is None or len(self.sxr) != nfft:
            self.sxr, self.srr = sxr, srr
        else:
            self.sxr = self.sxr * self.decay + sxr # type: ignore
            self.srr = self.srr * self.decay + srr # type: ignore
        f = (np.arange(nfft) - nfft // 2) * (lk.Fs / nfft)
        edge = (1 + lk.beta) * lk.baud / 2
        return f, (np.abs(f) <= edge) & (self.srr > 1e-3 * self.srr.max())
