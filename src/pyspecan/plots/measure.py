"""Measurement plots that are not markers on a frequency trace: CCDF and power vs time

Channel power, ACPR and occupied bandwidth are marker kinds, see markers.py.
"""
import numpy as np

from ..measure import CCDF as _CCDF
from ..measure import channel, units, windows
from .base import Plot, plot
from .frame import Axis, Frame, Marker, Trace, GREEN, RED, YELLOW
from .freq import POWER_UNIT, FreqPlot, _ref_level, fmt_hz, freq_text, hz
from .settings import Setting, override, without

def _db(p: float) -> float:
    return float(units.lin_to_db(p))

@plot("CCDF")
class CCDFPlot(Plot):
    """Complementary CDF of the instantaneous power, accumulated over every block since the last reset"""
    TITLE = "CCDF"
    SETTINGS = (
        Setting("bins", "Bins", "int", default=1000, min=100, max=20000, step=100, reset=True, help="histogram bins over 160 dB", group="Measurement"),
        Setting("show_gauss", "Gaussian ref", "check", default=True, help="the CCDF of Gaussian noise", group="Measurement"),
    )

    def reset(self):
        self.ccdf = _CCDF(self.bins) # type: ignore

    def render(self):
        samples = self.source.samples
        if not len(samples):
            return None
        self.ccdf.update(samples)
        x, p = self.ccdf.curve()
        keep = p >= 1e-8
        x, p = x[keep], p[keep]
        xmax = max(12.0, float(x.max()) + 1.0) if len(x) else 12.0
        traces = []
        if self.show_gauss: # type: ignore
            gx = np.linspace(0, xmax, 200)
            traces.append(Trace(-(10.0 ** (gx / 10.0)) * np.log10(np.e), gx, color=RED, name="gauss", width=1.0))
        traces.append(Trace(np.log10(p), x, color=YELLOW, name="ccdf"))
        s = self.ccdf.stats()
        f = lambda v: "-" if not np.isfinite(v) else f"{v:.2f} dB"
        readout = [("Samples", f"{self.ccdf.total}"), ("Average", f(s["avg"])), ("Peak", f(s["peak"])), ("PAPR", f(s["papr"]))]
        readout += [(f"{pc:g}%", f(s[f"p{pc:g}"])) for pc in (10, 1, 0.1, 0.01)]
        return Frame([Axis(
            xmin=0, xmax=xmax, ymin=-6, ymax=0, yfmt="log10", xlabel="dB above average", ylabel="P(> x)", traces=traces,
        )], title=self.TITLE, readout=readout)

@plot("Power vs Time")
class PowerVsTime(FreqPlot):
    """Band power of every overlapped (realtime) frame, scrolling. Time resolution is hop / fs"""
    TITLE = "Power vs Time"
    MARKERS = False
    SETTINGS = override(without(FreqPlot.SETTINGS, "vbw"), scale_div={"default": 5.0}) + (
        Setting("pvt_freq", "Center freq", "text", default="", coerce=freq_text, hint="center", help="band center frequency", group="Measurement"),
        Setting("pvt_bw", "Bandwidth", "text", default="", coerce=freq_text, hint="0 = wideband", help="band width, 0 or blank for the whole band", group="Measurement"),
        Setting("history", "History", "int", default=500, min=2, max=100000, reset=True, help="frames kept", group="Measurement"),
    )

    def reset(self):
        super().reset()
        self._hist = np.empty(0)

    def render(self):
        spectra = self.source.spectra("rt", self.window)
        if not len(spectra):
            return None
        fs, n = self.source.fs, spectra.shape[-1]
        db = units.scale(spectra, fs, windows.window(self.window, n), self.unit, self.cal_db, self.ext_gain)
        dens = self.density_lin(db) if db.ndim == 1 else np.vstack([self.density_lin(r) for r in db])
        freqs = self.bin_freqs(n)
        bw = hz(self.pvt_bw, 0.0) # type: ignore
        if bw > 0:
            c = hz(self.pvt_freq, self.source.cf) # type: ignore
            lo, hi = c - bw/2, c + bw/2
        else:
            lo, hi = freqs[0] - fs/n/2, freqs[-1] + fs/n/2
        power = np.atleast_1d(channel.band_power(dens, freqs, lo, hi))
        self._hist = np.concatenate((self._hist, units.lin_to_db(power)))[-self.history:] # type: ignore
        h = self._hist
        dt = self.source.hop("rt", n) / fs
        btm, top = self.y_range(h)
        x = (np.arange(len(h)) - len(h) + 1) * dt
        lin_mean = float(np.mean(units.db_to_lin(h)))
        u = POWER_UNIT[self.unit]
        return Frame([Axis(
            xmin=-(self.history - 1) * dt, xmax=0, ymin=btm, ymax=top, offscale=self.offscale(h, btm, top), # type: ignore
            xfmt="time", xlabel="Time", ylabel=u, traces=[Trace(h, x, name="pvt")],
        )], title=self.TITLE, readout=[
            ("Band", "wideband" if bw <= 0 else f"{fmt_hz(c)}, {fmt_hz(bw)}"), # type: ignore
            ("Average", f"{_db(lin_mean):.2f} {u}"), ("Peak", f"{h.max():.2f} {u}"), ("Min", f"{h.min():.2f} {u}"),
            ("Resolution", f"{dt*1e3:.3g} ms"),
        ])

@plot("Occupancy")
class Occupancy(FreqPlot):
    """Spectrum occupancy: the share of the overlapped (realtime) frames in which each bin is above a threshold,
    counted since the last reset. The live spectrum is drawn above it with the threshold as a line to drag"""
    TITLE = "Occupancy"
    MARKERS = False # the % axis is not a level
    SETTINGS = override(FreqPlot.SETTINGS, vbw={"default": 0.0}) + (
        Setting("threshold", "Threshold", "text", default="auto", coerce=_ref_level, hint="auto", reset=True, group="Measurement",
                help="level a bin must pass to count as occupied ('auto': 10 dB over the median of the first block)"),
        Setting("points", "Points", "int", default=1001, min=0, max=65536, step=100, hint="0 = all bins", group="Display", advanced=True,
                help="display points (peak detector), 0 for every bin"),
    )

    def reset(self):
        super().reset()
        self.counts: np.ndarray | None = None
        self.frames = 0
        self.thr: float | None = None # the threshold in use, resolved from "auto" once

    def render(self):
        rows = self.psd_rows("rt", smooth=False)
        if not len(rows):
            return None
        if self.thr is None:
            self.thr = float(np.median(rows) + 10.0) if self.threshold == "auto" else float(self.threshold)
        if self.counts is None or len(self.counts) != rows.shape[-1]:
            self.counts, self.frames = np.zeros(rows.shape[-1]), 0
        self.counts += (rows > self.thr).sum(axis=0)
        self.frames += len(rows)
        pct = 100.0 * self.counts / self.frames
        self.last = rows[-1]
        live = self.smooth(self.last)
        btm, top = self.y_range(self.last)
        fmin, fmax = self.source.freq_range()
        lx, ly = self.reduced(live, self.points)
        px, py = self.reduced(pct, self.points)
        u = self.unit
        return Frame([
            Axis(xmin=fmin, xmax=fmax, xfmt="freq", ymin=btm, ymax=top, offscale=self.offscale(self.last, btm, top), ylabel=u,
                 traces=[Trace(ly, lx, name="live")],
                 markers=[Marker(0.0, self.thr, "threshold", RED, kind="hline", edit="threshold")]),
            Axis(xmin=fmin, xmax=fmax, xfmt="freq", ymin=0.0, ymax=100.0, ylabel="% of frames",
                 traces=[Trace(py, px, color=GREEN, name="occupancy")]),
        ], title=self.TITLE, readout=[
            ("Frames", str(self.frames)), ("Threshold", f"{self.thr:.1f} {u}"),
            ("Occupied", f"{pct.mean():.1f}%"), ("Bins > 50%", f"{100.0 * np.mean(pct > 50):.1f}%"),
        ])
