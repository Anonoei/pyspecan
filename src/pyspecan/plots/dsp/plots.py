"""DSP plots of the selected signal: constellation, eye diagram and its channel's response (network analyzer)

They analyse the signal the "Analysis" globals select (pick one by clicking its box from the `signals` marker on
any spectrum), see analyzer.py for how it is found and locked.
"""
import numpy as np

from ..base import Plot, plot
from ..frame import BLUE, GREEN, IMAGE, LINE, RED, SCATTER, THREE_D, YELLOW, Axis, Frame, Image, Marker, Table, TableRow, Trace, fmt_time, time_unit
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
        )], title=self.TITLE, readout=[*self.sel_readout(sel), *self.lock_readout(lk), *error_summary(lk)])

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

@plot("Vector Diagram")
class VectorDiagram(DSPPlot):
    """The constellation with the path between the symbols: the matched filter's output drawn as a line, so the
    transitions show (a filtered PSK passing near the origin, an offset QPSK that never does, a timing error smearing
    the arrivals)"""
    TITLE = "Vector Diagram"
    FEATURES = frozenset({LINE, SCATTER})
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("count", "Symbols", "int", default=200, min=4, max=5000, step=50, group="Display", help="latest symbols drawn"),
        Setting("marks", "Mark symbols", "check", default=True, group="Display", help="mark the symbol instants"),
    )

    def render(self):
        sel, lk, why = self.analyse()
        lim = 1.5
        if lk is None:
            return self.empty([Axis(xmin=-lim, xmax=lim, ymin=-lim, ymax=lim, square=True, xlabel="I", ylabel="Q")], sel, why)
        n = min(self.count, len(lk.syms))
        k0 = len(lk.syms) - n
        t, z = matched(lk, 8)
        on = (t >= k0 - 0.5) & (t <= len(lk.syms) - 0.5)
        path = z[on]
        lim = max(1.5, 1.1 * float(np.max(np.abs(path))) if len(path) else 1.5)
        traces = [Trace(path.imag, path.real, color=BLUE, alpha=0.55, width=1.0, name="path")]
        if self.marks:
            s = lk.syms[k0:]
            traces.append(Trace(s.imag, s.real, color=YELLOW, kind=SCATTER, name="syms"))
        traces.append(Trace(lk.points.imag, lk.points.real, color=RED, kind=SCATTER, name="ideal"))
        return Frame([Axis(xmin=-lim, xmax=lim, ymin=-lim, ymax=lim, square=True, xlabel="I", ylabel="Q", traces=traces)],
                     title=self.TITLE, readout=[*self.sel_readout(sel), *self.lock_readout(lk)])

@plot("Constellation Density")
class ConstellationDensity(DSPPlot):
    """The symbols as a heat map, built up over blocks, under the ideal points: how the symbols spread around each
    point (round for noise, stretched along the circle for phase noise, along the radius for compression) shows where
    a scatter of dots only overlaps"""
    TITLE = "Constellation Density"
    FEATURES = frozenset({IMAGE, SCATTER})
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("bins", "Bins", "int", default=160, min=32, max=1024, group="Display", help="cells across each axis"),
        Setting("ideal", "Ideal points", "check", default=True, group="Display", help="the ideal points over the density"),
        SETTING_DECAY.with_(default=0.9), SETTING_CMAP.with_(default="hot"),
    )

    def reset(self):
        super().reset()
        self.changed_lock()

    def changed_lock(self):
        self.hist = None

    def changed(self, key):
        if key == "bins":
            self.hist = None

    def render(self):
        sel, lk, why = self.analyse()
        lim = 1.5
        if lk is None:
            return self.empty([Axis(xmin=-lim, xmax=lim, ymin=-lim, ymax=lim, square=True, xlabel="I", ylabel="Q")], sel, why)
        lim = max(1.5, 1.3 * float(np.max(np.abs(lk.points))))
        h, _, _ = np.histogram2d(lk.syms.imag, lk.syms.real, self.bins, range=[[-lim, lim], [-lim, lim]]) # type: ignore
        h = h[::-1] # row 0 is the top: +Q
        self.hist = h if self.hist is None or self.hist.shape != h.shape else self.hist * self.decay + h # type: ignore
        top = float(self.hist.max())
        img = np.rint(np.log1p(self.hist) * (255.0 / np.log1p(top))) if top > 0 else np.zeros_like(self.hist)
        traces = [Trace(lk.points.imag, lk.points.real, color=BLUE, kind=SCATTER, name="ideal")] if self.ideal else []
        return Frame([Axis(xmin=-lim, xmax=lim, ymin=-lim, ymax=lim, square=True, xlabel="I", ylabel="Q",
                           image=Image(img.astype(np.uint8), cmap=self.cmap), traces=traces)], # type: ignore
                     title=self.TITLE, readout=[*self.sel_readout(sel), *self.lock_readout(lk), *error_summary(lk)[:4]])

@plot("3D Constellation")
class Constellation3D(DSPPlot):
    """The selected signal's I and Q against time: the matched filter's path between symbols and the symbols on it, a
    constellation unrolled along the time axis"""
    TITLE = "3D Constellation"
    FEATURES = frozenset({LINE, SCATTER, THREE_D})
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("count", "Symbols", "int", default=48, min=4, max=2000, step=8, group="Display", help="latest symbols shown"),
        Setting("path", "Path", "check", default=True, group="Display", help="the waveform between the symbols"),
    )

    def render(self):
        sel, lk, why = self.analyse()
        lim = 1.5
        if lk is None:
            return self.empty([Axis(projection="3d", aspect=(3, 1, 1), xmin=0, xmax=1, ymin=-lim, ymax=lim, zmin=-lim, zmax=lim,
                                    xlabel="Symbols", ylabel="I")], sel, why)
        lim = max(1.5, 1.2 * float(np.max(np.abs(lk.points))))
        n = min(self.count, len(lk.syms))
        k0 = len(lk.syms) - n
        k = np.arange(n, dtype=float) # counted from the first one shown
        s = lk.syms[k0:]
        traces = []
        if self.path:
            t, z = matched(lk, 8)
            on = (t >= k0) & (t <= k0 + n - 1)
            traces.append(Trace(z.real[on], t[on] - k0, z=z.imag[on], color=BLUE, alpha=0.6, width=1.0, name="path"))
        traces.append(Trace(s.real, k, z=s.imag, color=YELLOW, kind=SCATTER, name="syms"))
        return Frame([Axis(
            xmin=float(k[0]), xmax=float(k[-1]), ymin=-lim, ymax=lim, zmin=-lim, zmax=lim, projection="3d", aspect=(3, 1, 1),
            xlabel="Symbols", ylabel="I", traces=traces,
        )], title=self.TITLE, readout=[*self.sel_readout(sel), *self.lock_readout(lk)])

@plot("Error Vector")
class ErrorVector(DSPPlot):
    """Per symbol: the error vector magnitude, the magnitude error and the phase error against the decided points"""
    TITLE = "Error Vector"
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("count", "Symbols", "int", default=500, min=16, max=20000, step=100, group="Display", help="latest symbols shown"),
    )

    def render(self):
        sel, lk, why = self.analyse()
        if lk is None:
            return self.empty([Axis(ylabel="EVM (%)"), Axis(ylabel="Mag err (%)"), Axis(ylabel="Phase err (deg)")], sel, why)
        _, evm, mag, ph = errors(lk)
        n = min(self.count, len(evm))
        k = np.arange(n, dtype=float) # counted from the first one shown
        def sym(v, least):
            a = max(least, float(np.max(np.abs(v))) * 1.2)
            return -a, a
        mlo, mhi = sym(mag[-n:], 5.0)
        plo, phi = sym(ph[-n:], 5.0)
        x0, x1 = float(k[0]), float(k[-1])
        return Frame([
            Axis(xmin=x0, xmax=x1, ymin=0.0, ymax=max(5.0, float(evm[-n:].max()) * 1.2), ylabel="EVM (%)",
                 traces=[Trace(evm[-n:], k, color=YELLOW, name="evm")]),
            Axis(xmin=x0, xmax=x1, ymin=mlo, ymax=mhi, ylabel="Mag err (%)", traces=[Trace(mag[-n:], k, color=GREEN, name="mag")]),
            Axis(xmin=x0, xmax=x1, ymin=plo, ymax=phi, ylabel="Phase err (deg)", xlabel="Symbol",
                 traces=[Trace(ph[-n:], k, color=BLUE, name="phase")]),
        ], title=self.TITLE, readout=[*self.sel_readout(sel), ("Mod", lk.mod), ("EVM", f"{lk.evm:.2f}% rms"), *error_summary(lk)])

def welch(x: np.ndarray, nfft: int) -> np.ndarray:
    """Mean |X|^2 of hann windowed segments overlapping by half (fftshifted)"""
    win = np.hanning(nfft)
    starts = np.arange(0, len(x) - nfft + 1, nfft // 2)
    if not len(starts):
        return np.zeros(nfft)
    X = np.fft.fftshift(np.fft.fft(x[starts[:, None] + np.arange(nfft)] * win, axis=1), axes=1)
    return np.mean(np.abs(X)**2, axis=0)

@plot("Error Vector Spectrum")
class ErrorVectorSpectrum(DSPPlot):
    """The spectrum of the error waveform (what was received minus the ideal waveform of the decided symbols) over
    the signal's: where in the band the errors are, an interferer or a filter's edge shows up here"""
    TITLE = "Error Vector Spectrum"
    SETTINGS = DSPPlot.SETTINGS + (SETTING_DECAY.with_(default=0.7),)

    def reset(self):
        super().reset()
        self.changed_lock()

    def changed_lock(self):
        self.se = self.ss = None

    def render(self):
        sel, lk, why = self.analyse()
        if lk is None:
            return self.empty([Axis(xfmt="freq", ylabel="dB")], sel, why)
        nfft = int(2 ** np.ceil(np.log2(max(64, 16 * lk.sps))))
        xr, r = pair(lk)
        g = np.vdot(r, xr) / max(np.vdot(r, r).real, 1e-30) # the received waveform's gain and phase on the ideal
        se, ss = welch(xr - g * r, nfft), welch(xr, nfft)
        if self.se is None or len(self.se) != nfft:
            self.se, self.ss = se, ss
        else:
            self.se, self.ss = self.se * self.decay + se, self.ss * self.decay + ss
        ref = float(self.ss.max()) or 1.0
        f = sel.freq + (np.arange(nfft) - nfft // 2) * (lk.Fs / nfft) # type: ignore
        sdb, edb = 10 * np.log10(self.ss / ref + 1e-30), 10 * np.log10(self.se / ref + 1e-30)
        inband = np.abs(f - sel.freq) <= lk.baud / 2 # type: ignore
        ratio = 10 * np.log10(np.sum(self.se[inband]) / max(np.sum(self.ss[inband]), 1e-30))
        return Frame([Axis(
            xmin=float(f[0]), xmax=float(f[-1]), xfmt="freq", ymin=max(-100.0, float(edb.min()) - 10), ymax=5.0, ylabel="dB",
            traces=[Trace(sdb, f, color=BLUE, alpha=0.5, width=1.0, name="signal"), Trace(edb, f, color=YELLOW, name="error")],
        )], title=self.TITLE, readout=[*self.sel_readout(sel), ("Mod", lk.mod), ("Error / signal", f"{ratio:.1f} dB in band"),
                                       ("EVM", f"{lk.evm:.2f}%")])

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

@plot("Network Analyzer")
class NetworkAnalyzer(ResponseMixin, DSPPlot):
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

    def render(self):
        sel, lk, why = self.analyse()
        if lk is None:
            return self.empty([Axis(ylabel="Magnitude (dB)"), Axis(ylabel="Phase (deg)"), Axis(ylabel="Group delay")], sel, why)
        f, band = self.accumulate(lk)
        edge = (1 + lk.beta) * lk.baud / 2
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

@plot("Impulse Response")
class ImpulseResponse(ResponseMixin, DSPPlot):
    """The link's impulse response: the network analyzer's frequency response, tapered (a hard band edge rings at
    -13 dB) and inverse transformed. The main path is at 0, each echo shows by its delay and level. A band limited
    signal can not show delays much finer than one over its bandwidth (the resolution in the readout): closer echoes
    widen the main path instead of standing apart"""
    TITLE = "Impulse Response"
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("resolution", "Points / symbol rate", "int", default=32, min=4, max=256, group="Display",
                help="frequency points per symbol rate: the delays shown span that many symbols"),
        Setting("taper", "Taper", "select", default="hann", options=("hann", "blackman"), group="Display",
                help="hann: finer delays, sidelobes at -31 dB. blackman: wider, sidelobes under -58 dB (weaker echoes show)"),
        SETTING_DECAY.with_(default=0.8),
    )
    TAPERS: dict = {"hann": (np.hanning, 2.0, -28.0), "blackman": (np.blackman, 3.0, -45.0)} # window, width (1/BW), echo floor

    def reset(self):
        super().reset()
        self.changed_lock()

    def render(self):
        sel, lk, why = self.analyse()
        if lk is None:
            return self.empty([Axis(xfmt="time", ylabel="dB")], sel, why)
        win, width, floor = self.TAPERS[self.taper] # type: ignore
        f, band = self.accumulate(lk)
        nfft = len(f)
        idx = np.flatnonzero(band)
        H = np.zeros(nfft, complex)
        H[idx] = self.sxr[idx] / self.srr[idx] * win(len(idx) + 2)[1:-1] # type: ignore
        h = np.fft.fftshift(np.fft.ifft(np.fft.ifftshift(H)))
        main = int(np.argmax(np.abs(h)))
        h = np.roll(h, nfft // 2 - main) # the main path at 0
        db = 20 * np.log10(np.abs(h) / max(float(np.abs(h).max()), 1e-30) + 1e-12)
        t = (np.arange(nfft) - nfft // 2) / lk.Fs
        res = width / max(float(f[idx[-1]] - f[idx[0]]), 1.0) # the tapered main path's half width
        readout = [*self.sel_readout(sel), ("Mod", lk.mod), ("Resolution", fmt_time(res))]
        from ...measure import peaks
        echoes = [int(j) for j in peaks.find_peaks(db, 8, floor, 1.0) if abs(t[j]) >= res] # over the taper's sidelobes
        for j in echoes[:3]:
            readout.append(("Echo", f"{db[j]:.1f} dB at {fmt_time(t[j])}"))
        if not echoes:
            readout.append(("Echoes", f"none over {floor:g} dB"))
        return Frame([Axis(
            xmin=float(t[0]), xmax=float(t[-1]), xfmt="time", ymin=-60.0, ymax=5.0, xlabel="Delay", ylabel="dB",
            traces=[Trace(db, t, color=YELLOW, name="h")],
        )], title=self.TITLE, readout=readout)

@plot("Cyclic Spectrum")
class CyclicSpectrum(DSPPlot):
    """Cyclostationary features of the selected signal, no lock needed: the spectral correlation's peak at each cycle
    frequency (the symbol rate and its multiples stand out for a linear modulation), the spectral coherence over
    frequency and cycle frequency, and what rpps reads from them (rate, carrier symmetry, offset, envelope)"""
    TITLE = "Cyclic Spectrum"
    FEATURES = frozenset({LINE, IMAGE})
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("channels", "Channels", "int", default=64, min=16, max=512, step=16, group="Processing", advanced=True,
                help="frequency channels (resolution fs / channels)"),
        Setting("samples", "Samples", "int", default=4096, min=512, max=65536, step=512, group="Processing",
                help="baseband samples used (cycle frequency resolution)"),
        SETTING_DECAY, SETTING_CMAP.with_(default="radar"),
    )

    def reset(self):
        super().reset()
        self.changed_lock()

    def changed_lock(self):
        self.prof = self.coh = None

    def render(self):
        from rpps.analysis.spectrum.cyclic import alpha_profile, features
        from rpps.analysis.spectrum.scf import coherence
        if not len(self.source.samples):
            return None
        an = analyzer(self.source)
        sel = an.selection(self.dsp_freq, self.dsp_bw) # type: ignore
        if sel is None:
            return self.empty([Axis(xfmt="freq", ylabel="|SCF|")], None, "no signal found")
        x, Fs = an.baseband(sel)
        x = x[-self.samples:] # type: ignore
        if len(x) < 4 * self.channels: # type: ignore
            return self.empty([Axis(xfmt="freq", ylabel="|SCF|")], sel, "too few samples")
        key = (sel.key, Fs)
        if key != self.sel_key:
            self.sel_key = key
            self.changed_lock()
        nch = self.channels # type: ignore
        a, prof = alpha_profile(x, Fs, nch)
        prof = prof / max(float(prof.max()), 1e-30)
        ff, aa, cc = coherence(x, Fs, nch)
        rows, cols = 96, 192
        grid = np.zeros((rows, cols))
        i = np.clip(((ff / Fs + 0.5) * rows).astype(int), 0, rows - 1)
        j = np.clip(((aa / Fs + 1) / 2 * cols).astype(int), 0, cols - 1)
        np.maximum.at(grid, (i, j), cc)
        grid[:, np.abs((np.arange(cols) + 0.5) / cols * 2 - 1) * Fs <= Fs / nch] = 0 # alpha = 0 is the power spectrum
        if self.prof is None or len(self.prof) != len(prof):
            self.prof, self.coh = prof, grid
        else:
            self.prof = self.prof * self.decay + prof * (1 - self.decay) # type: ignore
            self.coh = np.maximum(self.coh * self.decay, grid) # type: ignore
        readout = [*self.sel_readout(sel)]
        marks = []
        try:
            feat = features(x, Fs)
        except (ValueError, IndexError, FloatingPointError) as e:
            feat = None
            readout.append(("Features", str(e)))
        if feat is not None:
            if feat.baud is not None:
                readout.append(("Baud", f"{fmt_hz(feat.baud).replace('Hz', 'Bd')} ({feat.baud_from}, {feat.baud_line.db:.1f} dB)"))
                for m in (-1, 1):
                    marks.append(Marker(m * feat.baud, 0.0, "baud" if m > 0 else "", RED, kind="vline"))
            else:
                readout.append(("Baud", "no rate line"))
            if feat.order is not None:
                from rpps.analysis.spectrum.cyclic import ORDER_NAMES
                readout.append(("Carrier", f"x^{feat.order} line, {ORDER_NAMES.get(feat.order, '')}, CFO {fmt_hz(feat.cfo)}"))
            readout.append(("Envelope", f"{feat.envelope:.2f} (1 constant, 2 Gaussian)"))
        img = np.rint(self.coh / max(float(self.coh.max()), 1e-12) * 255).astype(np.uint8)[::-1] # type: ignore
        return Frame([
            Axis(xmin=float(-Fs), xmax=float(Fs), xfmt="freq", ymin=0.0, ymax=1.05, xlabel="Cycle frequency", ylabel="|SCF| (rel)",
                 traces=[Trace(self.prof, a, color=YELLOW, name="profile")], markers=marks),
            Axis(xmin=float(-Fs), xmax=float(Fs), xfmt="freq", ymin=float(-Fs / 2), ymax=float(Fs / 2), yfmt="freq",
                 xlabel="Cycle frequency", ylabel="Frequency", image=Image(img, cmap=self.cmap)),
        ], title=self.TITLE, readout=readout)

@plot("Symbol Table")
class SymbolTable(DSPPlot):
    """The decided symbols: each one's point in the constellation (rpps' point order) in a table, eight to a row, and
    against time. The carrier's phase ambiguity (any of the constellation's symmetric rotations) is not resolved"""
    TITLE = "Symbol Table"
    FEATURES = frozenset({SCATTER})
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("count", "Symbols", "int", default=128, min=8, max=2048, step=8, group="Display", help="latest symbols listed"),
    )

    def render(self):
        sel, lk, why = self.analyse()
        if lk is None:
            return self.empty([Axis(ylabel="Symbol")], sel, why)
        idx = np.argmin(np.abs(lk.syms[:, None] - lk.points[None, :]), axis=1)
        n = min(self.count, len(idx))
        first = len(idx) - n
        width = max(1, int(np.ceil(np.log2(len(lk.points)) / 4))) # hex digits
        rows = []
        for r in range(0, n, 8):
            chunk = idx[first + r:first + r + 8]
            rows.append(TableRow(str(r), [str(r), *[format(int(v), f"0{width}X") for v in chunk]]))
        k = np.arange(n, dtype=float) # counted from the first one listed
        return Frame([Axis(
            xmin=float(k[0]), xmax=float(k[-1]), ymin=-0.5, ymax=len(lk.points) - 0.5, xlabel="Symbol", ylabel="Point",
            traces=[Trace(idx[first:].astype(float), k, color=YELLOW, kind=SCATTER, name="syms")],
        )], title=self.TITLE, readout=[*self.sel_readout(sel), ("Mod", lk.mod), ("Bits / symbol", f"{np.log2(len(lk.points)):g}")],
            table=Table(["Symbol", *[f"+{c}" for c in range(8)]], rows))
