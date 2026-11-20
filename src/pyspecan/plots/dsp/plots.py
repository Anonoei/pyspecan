"""DSP plots of the selected signal: constellation, eye diagram and its channel's response (network analyzer)

They analyse the signal the "Analysis" globals select (pick one by clicking its box from the `signals` marker on
any spectrum), see analyzer.py for how it is found and locked.
"""
import numpy as np

from ..base import Plot, plot
from ..frame import BLUE, GREEN, IMAGE, LINE, RED, SCATTER, YELLOW, Axis, Frame, Image, Trace, fmt_time, time_unit
from ..freq import SETTING_CMAP, fmt_hz
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
        except NoLock as e:
            return sel, None, str(e)
        except (ValueError, IndexError, FloatingPointError) as e: # nothing that looks like symbols
            return sel, None, f"no lock ({e})"
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

@plot("Constellation")
class Constellation(DSPPlot):
    """The selected signal's symbols after timing, carrier and gain recovery, over the ideal points"""
    TITLE = "Constellation"
    FEATURES = frozenset({SCATTER})
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("count", "Symbols", "int", default=1000, min=16, max=20000, step=100, group="Display", help="latest symbols shown"),
    )

    def render(self):
        sel, lk, why = self.analyse()
        lim = 1.5
        if lk is None:
            return self.empty([Axis(xmin=-lim, xmax=lim, ymin=-lim, ymax=lim, square=True, xlabel="I", ylabel="Q")], sel, why)
        s = lk.syms[-self.count:]
        lim = max(1.5, 1.2 * float(np.max(np.abs(lk.points)))) # type: ignore
        return Frame([Axis(
            xmin=-lim, xmax=lim, ymin=-lim, ymax=lim, square=True, xlabel="I", ylabel="Q",
            traces=[Trace(s.imag, s.real, color=YELLOW, kind=SCATTER, name="syms"),
                    Trace(lk.points.imag, lk.points.real, color=RED, kind=SCATTER, name="ideal")],
        )], title=self.TITLE, readout=[*self.sel_readout(sel), *self.lock_readout(lk), ("Symbols", str(len(lk.syms)))])

def eye_points(lk: Lock, cols: int = 128) -> tuple[np.ndarray, np.ndarray]:
    """(position in [0, 2) symbols, matched filter output) of the selection's waveform, interpolated finer than `cols`
    columns across two symbols (sample spacing would leave stripes). The symbol instants are at 1 (and 0 / 2): the eye
    opens in the middle"""
    up = max(1, int(np.ceil(1.5 * cols / (2 * lk.sps))))
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
    return ((t + 1.0) % 2.0)[edge:-edge], zu[edge:-edge]

@plot("Eye Diagram")
class EyeDiagram(DSPPlot):
    """The selected signal's matched filter output folded over two symbols, I above Q, as a density"""
    TITLE = "Eye Diagram"
    FEATURES = frozenset({IMAGE})
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("cols", "Width", "int", default=128, min=32, max=1024, group="Display", advanced=True, help="cells across two symbols"),
        Setting("rows", "Height", "int", default=96, min=16, max=1024, group="Display", advanced=True, help="cells over the amplitude"),
        SETTING_DECAY, SETTING_CMAP.with_(default="hot"),
    )

    def reset(self):
        super().reset()
        self.changed_lock()

    def changed_lock(self):
        self.hist = None

    def changed(self, key):
        if key in ("cols", "rows"):
            self.hist = None

    def render(self):
        sel, lk, why = self.analyse()
        if lk is None:
            return self.empty([Axis(xmin=0, xmax=2, ymin=-1.5, ymax=1.5, xlabel="Symbols", ylabel=c) for c in ("I", "Q")], sel, why)
        u, z = eye_points(lk, self.cols)
        lim = 1.6 * float(max(np.max(np.abs(lk.points.real)), np.max(np.abs(lk.points.imag)), 0.5))
        rng = [[-lim, lim], [0.0, 2.0]]
        new = np.stack([np.histogram2d(part, u, (self.rows, self.cols), range=rng)[0][::-1] for part in (z.real, z.imag)])
        self.hist = new if self.hist is None or self.hist.shape != new.shape else self.hist * self.decay + new
        axes = []
        for k, name in enumerate(("I", "Q")):
            h = self.hist[k]
            top = float(h.max())
            img = np.rint(np.log1p(h) * (255.0 / np.log1p(top))) if top > 0 else np.zeros_like(h)
            axes.append(Axis(xmin=0.0, xmax=2.0, ymin=-lim, ymax=lim, xlabel="Symbols", ylabel=name,
                             image=Image(img.astype(np.uint8), cmap=self.cmap)))
        return Frame(axes, title=self.TITLE, readout=[*self.sel_readout(sel), *self.lock_readout(lk)[:4]])

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

@plot("Network Analyzer")
class NetworkAnalyzer(DSPPlot):
    """The selected link's frequency response: magnitude, phase and group delay across the signal, from its ideal
    waveform (the decided symbols through the ideal pulse) to what was received. Measured blind, on live traffic,
    the way a vector signal analyzer reads the channel from its equalizer: no stimulus is needed, so it shows the
    whole path (transmitter filters, the air, this receiver) and not one device on its own"""
    TITLE = "Network Analyzer"
    FEATURES = frozenset({LINE})
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("resolution", "Points / symbol rate", "int", default=16, min=4, max=128, group="Display",
                help="frequency resolution, points across one symbol rate"),
        SETTING_DECAY.with_(default=0.8),
    )

    def reset(self):
        super().reset()
        self.changed_lock()

    def changed_lock(self):
        self.sxr = self.srr = None

    def render(self):
        sel, lk, why = self.analyse()
        if lk is None:
            return self.empty([Axis(ylabel="Magnitude (dB)"), Axis(ylabel="Phase (deg)"), Axis(ylabel="Group delay")], sel, why)
        nfft = int(2 ** np.ceil(np.log2(max(16, self.resolution * lk.sps)))) # type: ignore
        sxr, srr = cross_spectra(lk.derotated(), reference(lk), nfft)
        if self.sxr is None or len(self.sxr) != nfft:
            self.sxr, self.srr = sxr, srr
        else:
            self.sxr = self.sxr * self.decay + sxr
            self.srr = self.srr * self.decay + srr
        f = (np.arange(nfft) - nfft // 2) * (lk.Fs / nfft)
        edge = (1 + lk.beta) * lk.baud / 2
        band = (np.abs(f) <= edge) & (self.srr > 1e-3 * self.srr.max())
        if band.sum() < 4:
            return self.empty([Axis(ylabel="Magnitude (dB)"), Axis(ylabel="Phase (deg)"), Axis(ylabel="Group delay")], sel, "too narrow")
        H = self.sxr[band] / self.srr[band]
        fb = f[band]
        mid = np.abs(fb) <= lk.baud / 4
        mag = 20 * np.log10(np.abs(H) + 1e-30)
        mag -= np.mean(mag[mid]) if mid.any() else np.mean(mag)
        ph = np.unwrap(np.angle(H))
        slope, icept = np.polyfit(fb, ph, 1) # a pure delay (and the phase) are not the channel's shape
        ph_dev = np.degrees(ph - (slope * fb + icept))
        gd = -np.diff(ph) / (2 * np.pi * np.diff(fb))
        gd_x = (fb[1:] + fb[:-1]) / 2
        gd_dev = gd - np.median(gd)
        scale, unit = time_unit(max(float(np.max(np.abs(gd_dev))), 1e-12) * 4)
        x0 = sel.freq # type: ignore
        xmin, xmax = x0 - edge, x0 + edge
        def rng(v, least):
            a = max(least, float(np.max(np.abs(v))) * 1.2)
            return -a, a
        mlo, mhi = rng(mag, 3.0)
        plo, phi = rng(ph_dev, 10.0)
        glo, ghi = rng(gd_dev / scale, 1.0)
        axes = [
            Axis(xmin=xmin, xmax=xmax, xfmt="freq", ymin=mlo, ymax=mhi, ylabel="Magnitude (dB)",
                 traces=[Trace(mag, x0 + fb, color=YELLOW, name="mag")]),
            Axis(xmin=xmin, xmax=xmax, xfmt="freq", ymin=plo, ymax=phi, ylabel="Phase (deg)",
                 traces=[Trace(ph_dev, x0 + fb, color=BLUE, name="phase")]),
            Axis(xmin=xmin, xmax=xmax, xfmt="freq", ymin=glo, ymax=ghi, ylabel=f"Group delay ({unit})",
                 traces=[Trace(gd_dev / scale, x0 + gd_x, color=GREEN, name="gd")]),
        ]
        delay = -slope / (2 * np.pi) # s, the linear phase taken out
        return Frame(axes, title=self.TITLE, readout=[
            *self.sel_readout(sel), ("Mod", lk.mod), ("Baud", fmt_hz(lk.baud).replace("Hz", "Bd")),
            ("Ripple", f"{np.ptp(mag):.2f} dB p-p"), ("Phase", f"{np.std(ph_dev):.2f}° rms"),
            ("GD", f"{np.ptp(gd_dev) / scale:.3g} {unit} p-p"), ("Delay", fmt_time(delay)),
            ("Es/N0", f"{lk.esn0:.1f} dB"),
        ])
