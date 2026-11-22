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
from .analyzer import SPAN, Lock, NoLock, Selection, analyzer, rrc

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


def errors(lk: Lock) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Per symbol: (error vector, EVM %, magnitude error %, phase error degrees) against the decided points"""
    d = lk.decisions()
    e = lk.syms - d
    rms = float(np.sqrt(np.mean(np.abs(lk.points)**2))) or 1.0
    mag = (np.abs(lk.syms) - np.abs(d)) / np.maximum(np.abs(d), 1e-12) * 100
    ph = np.degrees(np.angle(lk.syms * np.conj(d)))
    return e, np.abs(e) / rms * 100, mag, ph


def error_summary(lk: Lock) -> list[tuple[str, str]]:
    """What a VSA's error summary shows: peak EVM (and where), MER, magnitude / phase error, IQ offset, gain imbalance
    and quadrature error"""
    e, evm, mag, ph = errors(lk)
    k = int(np.argmax(evm))
    rms_evm = float(np.sqrt(np.mean(evm**2))) or 1e-9
    s = lk.syms
    out = [("EVM pk", f"{evm[k]:.1f}% (symbol {k} of {len(evm)})"), ("MER", f"{-20 * np.log10(rms_evm / 100):.1f} dB"),
           ("Mag err", f"{np.sqrt(np.mean(mag**2)):.2f}% rms"), ("Phase err", f"{np.sqrt(np.mean(ph**2)):.2f}° rms"),
           ("IQ offset", f"{20 * np.log10(max(abs(np.mean(e)), 1e-9)):.1f} dBc")]
    if len(lk.points) > 2 and np.std(lk.points.imag) > 0: # a two dimensional constellation
        ideal = np.std(lk.points.real) / np.std(lk.points.imag)
        out.append(("Gain imb", f"{20 * np.log10(np.std(s.real) / max(np.std(s.imag), 1e-12) / ideal):+.2f} dB"))
        rho = float(np.mean(s.real * s.imag) / max(np.std(s.real) * np.std(s.imag), 1e-12))
        out.append(("Quad err", f"{np.degrees(np.arcsin(np.clip(rho, -1, 1))):+.2f}°"))
    out.append(("Symbols", str(len(s))))
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
    than its samples: unit rms at the symbol instants, the carrier offset and phase taken out"""
    xr = lk.derotated()
    L = int(np.ceil(SPAN * lk.sps))
    h = rrc(np.arange(-L, L + 1) / lk.sps, lk.beta)
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


def reference(lk: Lock) -> np.ndarray:
    """The waveform the decided symbols make through the ideal (root raised cosine) transmit pulse, on x's samples"""
    d = lk.decisions()
    S = SPAN * lk.sps
    width = int(np.ceil(2 * S)) + 2
    idx = np.ceil(lk.centres - S).astype(np.int64)[:, None] + np.arange(width)
    w = rrc((idx - lk.centres[:, None]) / lk.sps, lk.beta)
    w /= np.sqrt(np.sum(w**2, axis=1, keepdims=True))
    r = np.zeros(len(lk.x), complex)
    ok = (idx >= 0) & (idx < len(r))
    np.add.at(r, idx[ok], (d[:, None] * w)[ok])
    return r


def pair(lk: Lock) -> tuple[np.ndarray, np.ndarray]:
    """(received, ideal) waveforms without their ends, where the ideal lacks the symbols outside the record"""
    cut = int(np.ceil(2 * SPAN * lk.sps))
    x, r = lk.derotated(), reference(lk)
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
