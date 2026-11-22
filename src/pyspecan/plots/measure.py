"""Measurement plots that are not markers on a frequency trace: CCDF, power vs time, occupancy, marker trend and
autocorrelation

Channel power, ACPR and occupied bandwidth are marker kinds, see markers.py.
"""
from collections import deque

import numpy as np

from ..measure import CCDF as _CCDF
from ..measure import channel, correlate, units, windows
from .base import About, Plot, plot
from .frame import BLUE, GREEN, RED, YELLOW, Axis, Frame, Marker, Trace, fmt_time
from .freq import POWER_UNIT, FreqPlot, _ref_level, fmt_hz, freq_text, hz
from .psd import PSD
from .settings import Setting, override, parse_time, time_text, without


def _db(p: float) -> float:
    return float(units.lin_to_db(p))

@plot("CCDF")
class CCDFPlot(Plot):
    """Complementary CDF of the instantaneous power, accumulated over every block since the last reset"""
    TITLE = "CCDF"
    CATEGORY = "Measurements"
    ABOUT = About(
        data="Every sample's instantaneous power over the average, accumulated over blocks",
        shows='The chance the power exceeds the average by x dB (log axis) with a Gaussian reference; '
              'PAPR and percentiles',
        use=('Measure peak to average power', 'Check amplifier compression (the curve falls short of the reference)'),
        cost=0.28,
    )
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
    CATEGORY = "Measurements"
    ABOUT = About(
        data="Every overlapped frame's power in the whole span or a channel, kept as a history",
        shows='Power against time, with its average, peak and minimum',
        use=('Measure bursts and pulse timing', "Watch a channel's power change: fading, AGC"),
        cost=1.7,
    )
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
    CATEGORY = "Measurements"
    ABOUT = About(
        data="Every overlapped frame's PSD compared to a threshold, counted per bin since the last reset",
        shows='The live spectrum with the threshold as a line to drag, and below it the share of frames '
              'each bin was above it',
        use=('Survey how much a band is used', 'Find intermittent users of a channel'),
        cost=0.79,
    )
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

TREND_COLORS = (YELLOW, RED, BLUE, GREEN, "#c678dd", "#56b6c2", "#e5a04b", "#a0a0a0")
TREND_AXES = 3 # most value axes (one per unit), the rest share the last

@plot("Marker Trend")
class MarkerTrend(PSD):
    """What the markers measure, against time: a PSD with its markers, and under it each marker's numbers (a level,
    a channel's power, ACPR, OBW, THD, a limit's margin...) over the last `history` blocks, one axis per unit. Link it
    to a PSD to trend that PSD's markers"""
    TITLE = "Marker Trend"
    CATEGORY = "Measurements"
    ABOUT = About(
        data="A PSD (the same traces, gate and markers); each block, every marker's measured numbers kept with the "
             "block's time",
        shows="The spectrum with the markers (hidden with Spectrum off), and under it each marker's numbers against "
              "time, one axis per unit (levels, dBc, Hz, dB)",
        use=("Watch a channel's power, ACPR or a limit margin drift while something warms up or is tuned",
             "Log a peak's frequency and level over minutes",
             "Link to a PSD to trend the markers set there"),
        cost=1.1,
    )
    SETTINGS = PSD.SETTINGS + (
        Setting("history", "History", "int", default=500, min=2, max=100000, reset=True, group="Trend",
                help="blocks kept"),
        Setting("spectrum", "Spectrum", "check", default=True, group="Trend",
                help="draw the spectrum the markers sit on (off: only the trends; the table stays)"),
    )

    def reset(self):
        super().reset()
        self.trend: dict[str, tuple[deque, deque, str]] = {} # "M1 level" -> (times, values, unit)
        self._clock = 0.0 # seconds of samples seen, for sources that do not say a block's time
        self._t0 = None

    def _now(self) -> float:
        t = self.source.time
        self._clock += len(self.source.samples) / self.source.fs
        if t is None:
            return self._clock
        if self._t0 is None:
            self._t0 = t - self._clock
        return t - self._t0

    def render(self):
        frame = super().render()
        if frame is None or self.last is None:
            return frame
        now = self._now()
        values = self.marker_values if len(self.markers) else {}
        for key in list(self.trend):
            if key not in values:
                del self.trend[key] # its marker is gone or measures something else now
        for key, (v, unit) in values.items():
            t = self.trend.get(key)
            if t is None or t[2] != unit:
                t = self.trend[key] = (deque(maxlen=self.history), deque(maxlen=self.history), unit) # type: ignore
            t[0].append(now)
            t[1].append(v)
        if not self.spectrum: # type: ignore
            frame.axes = frame.axes[1:] if len(frame.axes) > 1 else []
        frame.axes += self.trend_axes(now)
        if not self.trend:
            frame.readout.append(("Trend", "add a marker to trend what it measures"))
        return frame

    def trend_axes(self, now: float) -> list[Axis]:
        units_ = list(dict.fromkeys(u for _, _, u in self.trend.values()))
        groups = units_[:TREND_AXES - 1] + (["/".join(units_[TREND_AXES - 1:])] if len(units_) >= TREND_AXES else [])
        def group(u):
            return u if u in groups else groups[-1]
        span = max((now - t[0][0] for t in self.trend.values() if t[0]), default=0.0)
        axes = []
        for g in groups:
            traces, ys = [], []
            for k, (key, (ts, vs, u)) in enumerate(self.trend.items()):
                if group(u) != g:
                    continue
                x, y = np.asarray(ts) - now, np.asarray(vs)
                ys.append(y)
                traces.append(Trace(y, x, color=TREND_COLORS[k % len(TREND_COLORS)], name=key, width=1.2))
            y = np.concatenate(ys)
            lo, hi = float(y.min()), float(y.max())
            pad = max((hi - lo) * 0.1, 1.0 if g != "Hz" else max(abs(hi) * 1e-6, 1.0))
            axes.append(Axis(xmin=-max(span, 1e-3), xmax=0.0, ymin=lo - pad, ymax=hi + pad, xfmt="time",
                             yfmt="freq" if g == "Hz" else "num", xlabel="Time", ylabel=g, traces=traces))
        return axes


@plot("Autocorrelation")
class Autocorrelation(Plot):
    """|R(lag)|: how much the signal resembles itself a lag later, over the block (zero padded FFT), averaged over
    blocks. A symbol rate, an OFDM symbol (its cyclic prefix correlates at the useful length Tu), a frame or a
    repeated preamble each make a peak at their period, which the readout lists with its rate"""
    TITLE = "Autocorrelation"
    CATEGORY = "Time domain"
    ABOUT = About(
        data="The block (its mean taken out), correlated with itself at every lag up to the span by a zero padded FFT; "
             "averaged over blocks",
        shows="|R(lag)| / R(0) against the lag (linear or dB), the highest peaks past the main lobe that stand out "
              "from their surroundings (and over the noise's own, 4 / sqrt(samples)) marked with their lag and its rate",
        use=("Find an OFDM signal's useful symbol length (the cyclic prefix correlates at Tu)",
             "Find repetition: preambles, frames, a pulse repetition interval",
             "Tell noise (one spike at 0) from structured signals"),
        cost=1.3,
    )
    SETTINGS = (
        Setting("span", "Span", "text", default="auto", coerce=time_text, hint="auto, 100u, 5m", reset=True, group="Measurement",
                help="largest lag shown ('auto': one FFT); at most half the block"),
        Setting("scale", "Scale", "select", default="linear", options=("linear", "dB"), group="Display"),
        Setting("decay", "Decay", "number", default=0.7, min=0.0, max=0.99, step=0.05, group="Measurement",
                help="how much of the earlier blocks stays each block, 0 shows only the latest"),
        Setting("remove_dc", "Remove DC", "check", default=True, reset=True, group="Measurement",
                help="take the mean out first (a DC offset correlates at every lag)"),
        Setting("count", "Peaks", "int", default=3, min=0, max=10, group="Display", help="peaks marked past the main lobe"),
    )

    def reset(self):
        self.r: np.ndarray | None = None

    def render(self):
        x = np.asarray(self.source.samples)
        if len(x) < 4:
            return None
        fs = self.source.fs
        span = parse_time(self.span) # type: ignore
        lags = int(round(span * fs)) if span > 0 else self.source.nfft
        lags = max(2, min(lags, len(x) // 2))
        r = correlate.autocorr(x, lags, self.remove_dc) # type: ignore
        if self.r is None or len(self.r) != len(r):
            self.r = r
        else:
            self.r = self.decay * self.r + (1 - self.decay) * r # type: ignore
        r = self.r
        t = np.arange(len(r)) / fs
        found = correlate.peaks(r, self.count, floor=4 / np.sqrt(len(x))) # type: ignore # noise reads about 1/sqrt(n)
        db = self.scale == "dB" # type: ignore
        y = 10 * np.log10(np.maximum(r, 1e-6)) if db else r
        marks, readout = [], []
        for k, (lag, v) in enumerate(found, 1):
            yv = 10 * np.log10(max(v, 1e-6)) if db else v
            marks.append(Marker(lag / fs, yv, f"R{k}", GREEN))
            readout.append((f"R{k}", f"{fmt_time(lag / fs)} ({fmt_hz(fs / lag)}), {v:.3f}"))
        lobe = correlate.lobe_end(r)
        readout.insert(0, ("Main lobe", fmt_time(lobe / fs)))
        return Frame([Axis(
            xmin=0.0, xmax=t[-1], ymin=-40.0 if db else 0.0, ymax=0.0 if db else 1.05, xfmt="time", xlabel="Lag",
            ylabel="|R| (dB)" if db else "|R| / R(0)", traces=[Trace(y, t, name="r")], markers=marks,
        )], title=self.TITLE, readout=readout)
