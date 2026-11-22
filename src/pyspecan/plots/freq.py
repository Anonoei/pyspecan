"""Shared pieces of the frequency domain plots"""
from dataclasses import replace

import numpy as np

from ..measure import Averager, detector, units, windows
from ..measure.windows import WindowLUT
from ..obj import Frequency
from ..utils.vbw import vbw_rows
from . import colormap
from .base import Plot
from .frame import BLUE, GREEN, RED, YELLOW, Axis, Frame, Marker, Trace
from .settings import Setting


def _ref_level(value):
    if str(value).strip().lower() in ("", "auto"):
        return "auto"
    return float(value)

SETTING_CMAP = Setting("cmap", "Colors", "select", default="magma", options=tuple(colormap.names()), help="image color map", group="Display")

def to_psd(spectra: np.ndarray, fs: float, window: str = "blackman", unit: str = "dB/Hz", cal_db: float = 0.0, ext_gain_db: float = 0.0) -> np.ndarray:
    """(k, nfft) complex spectra of x * `window` -> dB in `unit`, corrected for the window's power"""
    return units.scale(spectra, fs, windows.window(window, spectra.shape[-1]), unit, cal_db, ext_gain_db)

def fmt_hz(v: float) -> str:
    """1234567 -> '1.235 MHz'"""
    a = abs(v)
    for scale, name in ((1e9, "GHz"), (1e6, "MHz"), (1e3, "kHz")):
        if a >= scale:
            return f"{v/scale:.4g} {name}"
    return f"{v:.4g} Hz"

def freq_text(value) -> str:
    """coerce for text settings holding a frequency like '1.2M', blank stays blank"""
    s = str(value).strip()
    if s:
        Frequency.get(s)
    return s

def freq_list_text(value) -> str:
    """coerce for text settings holding a comma separated list of frequencies"""
    parts = [p.strip() for p in str(value).split(",") if p.strip()]
    for p in parts:
        Frequency.get(p)
    return ", ".join(parts)

def hz(value: str, default: float) -> float:
    """A freq_text setting as Hz, `default` when blank"""
    return Frequency.get(value).raw if str(value).strip() else float(default)

def hz_list(value: str) -> list[float]:
    return [Frequency.get(p).raw for p in str(value).split(",") if p.strip()]

def optional_float(value) -> str:
    s = str(value).strip()
    if s:
        float(s)
    return s

POWER_UNIT = {"dB/Hz": "dB", "dBFS": "dBFS", "dBm": "dBm", "dBm/Hz": "dBm"}
DENSITY_UNIT = {"dB/Hz": "dB/Hz", "dBFS": "dBFS/Hz", "dBm": "dBm/Hz", "dBm/Hz": "dBm/Hz"}

class FreqPlot(Plot):
    """Plots with a frequency axis and a ref level / scale per division

    Plots that show a dB trace carry markers (MARKERS): they set `self.last`, the latest
    unsmoothed trace, and call `apply_markers(frame)` with the frame they built.
    """
    MARKERS = True
    LINK_DOMAIN = "spectrum"
    SETTINGS = (
        Setting("ref_level", "Ref level", "text", default="auto", coerce=_ref_level, hint="auto", help="ref level (number or 'auto')",
                group="Level", scope="link"),
        Setting("scale_div", "Scale / div", "number", default=10.0, min=0.0001, step=1, help="scale per division",
                group="Level", scope="link"),
        Setting("unit", "Unit", "select", default="dB/Hz", options=units.UNITS, reset=True, help="level unit",
                group="Level", scope="link"),
        Setting("vbw", "VBW", "number", default=10.0, min=0, step=1, reset=True, help="video bandwidth",
                group="Processing", scope="link"),
        Setting("window", "Window", "select", default="blackman", options=tuple(WindowLUT), reset=True, help="FFT window function",
                group="Processing", scope="link"),
    )

    def __init__(self, source, **kwargs):
        from .markers import MarkerSet  # markers import this module
        self.own_markers = MarkerSet()
        self.last = None
        self.marker_values: dict = {}
        super().__init__(source, **kwargs)

    @property
    def markers(self):
        """The link's shared markers while linked, each member measures them on its own trace"""
        return self.link.markers if self.link is not None and self.link.markers is not None else self.own_markers

    def reset(self):
        self._auto = None # resolved level while ref_level is "auto"
        self.last = None

    def changed(self, key):
        if key == "ref_level":
            self._auto = None
            if self.link is not None:
                self.link.auto = None

    def smooth(self, psd: np.ndarray) -> np.ndarray:
        """`psd` ((n,) or (k, n)) smoothed by the vbw"""
        return vbw_rows(psd, self.vbw) if self.vbw > 0 and len(psd) else psd

    def psd_rows(self, mode: str = "swept", smooth: bool = True) -> np.ndarray:
        """(k, nfft) psd of the frames in this tick's block (swept: back to back, rt: overlapped), smoothed by the vbw"""
        spectra = self.source.spectra(mode, self.window)
        psd = to_psd(spectra, self.source.fs, self.window, self.unit, self.cal_db, self.ext_gain)
        return self.smooth(psd) if smooth else psd

    # --- measurement helpers --- #
    def rbw(self, nfft: int | None = None) -> float:
        nfft = nfft or self.source.nfft
        return units.rbw(self.source.fs, nfft, windows.window(self.window, nfft))

    def bin_freqs(self, n: int) -> np.ndarray:
        """Frequency of each bin of a centered n point spectrum"""
        fmin, _ = self.source.freq_range()
        return fmin + np.arange(n) * (self.source.fs / n)

    def reduced(self, y: np.ndarray, points: int, mode: str = "peak") -> tuple[np.ndarray | None, np.ndarray]:
        """`y` (one value per bin) through the detector, with the frequency of each group's center.
        x is None when nothing was reduced (one point per bin, see Trace)"""
        n = len(y)
        x, out = detector.reduce(y, points, mode)
        if len(out) >= n:
            return None, out
        return self.bin_freqs(n)[0] + x * (self.source.fs / n), out

    def density_lin(self, y_db: np.ndarray) -> np.ndarray:
        """Trace in the plot's unit -> linear power per Hz, so integrating over frequency gives power"""
        lin = units.db_to_lin(y_db)
        if not units.is_density(self.unit):
            lin = lin / self.rbw(len(y_db))
        return lin

    def rbw_readout(self, n: int | None = None) -> list[tuple[str, str]]:
        return [("RBW", fmt_hz(self.rbw(n)))]

    def apply_markers(self, frame: Frame, image: bool = False):
        """Add the markers' marks, bands and table to the frame's first axis. On an image axis (no
        levels) a marker is a vertical line. What they measured stays in `marker_values` ({"M1 level": (value, unit)})"""
        if self.last is None:
            return
        marks, bands, table, self.marker_values = self.markers.evaluate(self, self.last, self.bin_freqs(len(self.last)))
        ax = frame.axes[0]
        if image:
            marks = [replace(m, y=0.0, kind="vline") if m.kind == "point" else m for m in marks
                     if m.kind != "hline" or ax.ymin is not None] # a level needs a level axis
        ax.markers += marks
        ax.bands += bands
        frame.table = table

    def resolve_ref(self, values) -> float:
        """The numeric ref level, "auto" is resolved from the first data seen"""
        if self.ref_level != "auto":
            return self.ref_level
        link = self.link
        auto = link.auto if link is not None else self._auto
        if auto is None: # linked plots use the level the first of them to render resolved
            vmax = float(np.nanmax(values)) if np.isfinite(values).any() else 0.0
            auto = int(vmax * 0.9) if vmax < 0 else int(vmax * 1.1)
            if link is not None:
                link.auto = auto
            else:
                self._auto = auto
        return auto

    def y_range(self, values) -> tuple[float, float]:
        top = self.resolve_ref(values)
        return top - 10*self.scale_div, top

    @staticmethod
    def offscale(values, btm, top) -> str | None:
        if np.all(values < btm):
            return "below"
        if np.all(values > top):
            return "above"
        return None

class HoldMixin:
    """Min / max hold traces"""
    SETTINGS = (
        Setting("show_max", "Max hold", "check", default=True, group="Trace"),
        Setting("show_min", "Min hold", "check", default=True, group="Trace"),
    )

    def reset_hold(self):
        self._max = self._min = None

    def changed(self, key):
        super().changed(key) # type: ignore
        if key == "show_max":
            self._max = None # restart the hold when toggled
        elif key == "show_min":
            self._min = None

    def hold(self, rows: np.ndarray):
        """Fold (k, n) rows into the holds"""
        if not len(rows):
            return
        hi, lo = rows.max(axis=0), rows.min(axis=0)
        if self._max is None or len(self._max) != len(hi):
            self._max = hi.copy()
        else:
            np.maximum(self._max, hi, out=self._max)
        if self._min is None or len(self._min) != len(lo):
            self._min = lo.copy()
        else:
            np.minimum(self._min, lo, out=self._min)

    def hold_traces(self, x=None) -> list[Trace]:
        out = []
        if self.show_max and self._max is not None: # type: ignore
            out.append(Trace(self._max, x, color=RED, name="max"))
        if self.show_min and self._min is not None: # type: ignore
            out.append(Trace(self._min, x, color=BLUE, name="min"))
        return out


WRITE, AVERAGE, MAX_HOLD, MIN_HOLD, VIEW, BLANK = "clear/write", "average", "max hold", "min hold", "view", "blank"
TRACE_MODES = (WRITE, AVERAGE, MAX_HOLD, MIN_HOLD, VIEW, BLANK)
TRACE_COLORS = (YELLOW, RED, BLUE, GREEN)
TRACE_DEFAULTS = (WRITE, MAX_HOLD, MIN_HOLD, BLANK) # what the PSD had before traces: live, max hold, min hold

class _TraceState:
    """What one trace holds: `data` full resolution, `smoothed` when it went through the vbw already (the holds fold
    smoothed rows, as an analyzer's video filter sits ahead of its trace detector)"""
    def __init__(self):
        self.data: np.ndarray | None = None
        self.smoothed = False
        self.avg: Averager | None = None

class TraceMixin:
    """Spectrum analyzer style traces: N_TRACES of them, each in a mode of its own and a color of its own

    clear/write: the newest row. average: the rows averaged (the "avg" kind over "avg_count" rows). max / min hold:
    the highest / lowest of every row since the mode was picked. view: frozen, keeps showing what it had.
    blank: not shown (what it had is kept, "view" shows it again). Picking a mode other than view / blank starts
    the trace over.

    Markers, measurements, "store ref" and trace math read the "marker_trace". Traces are reduced to display points
    by the detector, only what is drawn: markers read full resolution."""
    N_TRACES = len(TRACE_COLORS)
    SETTINGS = tuple(
        Setting(f"t{i}_mode", f"Trace {i}", "select", default=TRACE_DEFAULTS[i - 1], options=TRACE_MODES, group="Trace",
                help=f"what trace {i} shows: clear/write the newest, average, max / min hold, view (frozen), blank (hidden)")
        for i in range(1, len(TRACE_COLORS) + 1)
    ) + (
        Setting("marker_trace", "Marker trace", "select", default="1", options=tuple(str(i) for i in range(1, len(TRACE_COLORS) + 1)),
                group="Trace", help="the trace markers, measurements, store ref and trace math read"),
        Setting("avg", "Average", "select", default="power", options=("power", "log", "exp"), group="Trace",
                help="how the average traces average: power (mean in linear power), log (mean of dB), exp (exponential)"),
        Setting("avg_count", "Avg count", "int", default=10, min=1, max=10000, help="rows the average traces average", group="Trace"),
        Setting("detector", "Detector", "select", default="peak", options=detector.MODES, help="how bins are reduced to display points",
                group="Trace", advanced=True),
        Setting("points", "Points", "int", default=1001, min=0, max=65536, step=100, hint="0 = all bins", help="display points, 0 for every bin",
                group="Trace", advanced=True),
    )

    @classmethod
    def migrate(cls, settings: dict) -> dict:
        """The settings of before traces: show_max / show_min (traces 2 and 3) and avg "off" or a kind (trace 1)"""
        out = dict(settings)
        for old, key, mode in (("show_max", "t2_mode", MAX_HOLD), ("show_min", "t3_mode", MIN_HOLD)):
            if old in out:
                on = out.pop(old)
                on = on.strip().lower() in ("1", "true", "yes", "on") if isinstance(on, str) else bool(on)
                out.setdefault(key, mode if on else BLANK)
        if out.get("avg") == "off":
            del out["avg"]
        elif out.get("avg") in ("power", "log", "exp") and "t1_mode" not in out and "marker_trace" not in out:
            out["t1_mode"] = AVERAGE # an average then was of the live trace
        return super().migrate(out) # type: ignore

    def reset_traces(self):
        self._traces = [_TraceState() for _ in range(self.N_TRACES)]

    def mode(self, i: int) -> str:
        """Trace i's mode, i from 0"""
        return getattr(self, f"t{i + 1}_mode")

    def changed(self, key):
        super().changed(key) # type: ignore
        if key.startswith("t") and key.endswith("_mode") and key[1:-5].isdigit():
            i = int(key[1:-5]) - 1
            if self.mode(i) not in (VIEW, BLANK): # view / blank keep what it had, anything else starts over
                self._traces[i] = _TraceState()
        elif key in ("avg", "avg_count"):
            for i, t in enumerate(self._traces):
                if self.mode(i) == AVERAGE:
                    self._traces[i] = _TraceState()

    def fold(self, raw: np.ndarray):
        """Fold the block's (k, n) unsmoothed rows into the traces"""
        smoothed = None
        n = raw.shape[-1]
        for i, t in enumerate(self._traces):
            mode = self.mode(i)
            if mode in (VIEW, BLANK):
                if t.data is not None and len(t.data) != n: # another FFT size: what it held no longer fits
                    self._traces[i] = _TraceState()
                continue
            if t.data is not None and len(t.data) != n:
                t = self._traces[i] = _TraceState()
            if mode == WRITE:
                t.data, t.smoothed = raw[-1], False
            elif mode == AVERAGE:
                if t.avg is None:
                    t.avg = Averager(self.avg, self.avg_count) # type: ignore
                t.data, t.smoothed = t.avg.update(raw), False
            else:
                if smoothed is None:
                    smoothed = self.smooth(raw) # type: ignore
                row = smoothed.max(axis=0) if mode == MAX_HOLD else smoothed.min(axis=0)
                if t.data is None:
                    t.data = row.copy()
                else:
                    (np.maximum if mode == MAX_HOLD else np.minimum)(t.data, row, out=t.data)
                t.smoothed = True

    def trace_data(self, i: int) -> np.ndarray | None:
        """Trace i at full resolution, as measured (unsmoothed for clear/write and average), None when it has nothing"""
        return self._traces[i].data

    def trace_shown(self, i: int) -> np.ndarray | None:
        """Trace i at full resolution as drawn: through the vbw"""
        t = self._traces[i]
        if t.data is None:
            return None
        return t.data if t.smoothed else self.smooth(t.data) # type: ignore

    def marker_index(self) -> int:
        return int(self.marker_trace) - 1 # type: ignore

    def trace_list(self) -> list[Trace]:
        """The traces to draw, full resolution: the higher numbers under the lower ones, and the marker trace on top
        (last, views read the last trace under the mouse)"""
        mk = self.marker_index()
        order = [i for i in reversed(range(self.N_TRACES)) if i != mk] + [mk]
        out = []
        for i in order:
            y = self.trace_shown(i)
            if y is not None and self.mode(i) != BLANK:
                out.append(Trace(y, color=TRACE_COLORS[i], name=f"t{i + 1}"))
        return out

    def shrink(self, traces: list[Trace]) -> list[Trace]:
        """Pass traces through the detector, only what is displayed is reduced. A reduced trace gets the
        frequency of each group's center as x, so it lines up with the markers (which use bin frequencies)"""
        for t in traces:
            if t.x is None:
                t.x, t.y = self.reduced(t.y, self.points, self.detector) # type: ignore
        return traces

    def avg_readout(self) -> list[tuple[str, str]]:
        """How far along the average traces are: "Avg" for one, "T2 avg" ... for several"""
        avgs = [(i, t.avg) for i, t in enumerate(self._traces) if self.mode(i) == AVERAGE and t.avg is not None]
        if self.avg_count <= 1: # type: ignore
            return []
        return [("Avg" if len(avgs) == 1 else f"T{i + 1} avg", f"{a.n}/{self.avg_count} ({self.avg})") for i, a in avgs] # type: ignore


REF_COLOR = "#a0a0a0"
FLOOR = -300.0 # where a reference has no value (outside the span it was stored over)

class RefMixin:
    """A stored reference trace drawn under the live one, and trace math against it (live - ref, in dB, on an axis of
    its own). "store ref" keeps the live trace (averaged and smoothed, full resolution) with its frequencies, so a
    retune or another FFT size still lines it up; a change of level unit drops it"""
    ACTIONS = ("store ref", "clear ref")
    SETTINGS = (
        Setting("ref_show", "Show ref", "check", default=True, group="Reference", help="draw the stored reference trace"),
        Setting("math", "Trace math", "select", default="off", options=("off", "live - ref"), group="Reference",
                help="live - ref: the difference in dB under the spectrum"),
    )

    def act(self, action):
        if action == "store ref":
            if self.last is None: # type: ignore
                raise ValueError("nothing to store yet: step or play first")
            n = len(self.last) # type: ignore
            shown = getattr(self, "last_shown", None) # as drawn: a hold went through the vbw already
            shown = self.smooth(self.last) if shown is None else shown # type: ignore
            self.ref = (self.bin_freqs(n), np.array(shown, copy=True), self.unit) # type: ignore
        elif action == "clear ref":
            self.ref = None
        else:
            super().act(action) # type: ignore

    def ref_on(self, n: int) -> np.ndarray | None:
        """The reference on the current n bins (FLOOR where it was not stored), None without one"""
        ref = getattr(self, "ref", None)
        if ref is None:
            return None
        if ref[2] != self.unit: # type: ignore
            self.ref = None
            return None
        return np.interp(self.bin_freqs(n), ref[0], ref[1], left=FLOOR, right=FLOOR) # type: ignore

    def ref_frame(self, frame: Frame, live: np.ndarray):
        """Add the reference trace to the frame's first axis and, with trace math, the difference axis below it"""
        rf = self.ref_on(len(live))
        if rf is None:
            if self.math != "off": # type: ignore
                frame.readout.append(("Trace math", "store a reference first"))
            return
        ax = frame.axes[0]
        xr, yr = self.reduced(rf, self.points, self.detector) # type: ignore
        xr = self.bin_freqs(len(live)) if xr is None else xr # type: ignore
        keep = yr > FLOOR + 1
        if self.ref_show: # type: ignore
            ax.traces.insert(0, Trace(yr[keep], xr[keep], color=REF_COLOR, name="ref", width=1.0))
        if self.math == "live - ref": # type: ignore
            _, yl = self.reduced(live, self.points, self.detector) # type: ignore
            d = (yl - yr)[keep]
            lim = max(3.0, float(np.ceil(np.max(np.abs(d)) * 1.2))) if len(d) else 3.0
            frame.axes.append(Axis(xmin=ax.xmin, xmax=ax.xmax, xfmt="freq", ymin=-lim, ymax=lim, ylabel="live - ref (dB)",
                                   traces=[Trace(d, xr[keep], color=GREEN, name="diff")],
                                   markers=[Marker(0.0, 0.0, "", REF_COLOR, kind="hline")]))
            if len(d):
                frame.readout.append(("live - ref", f"mean {d.mean():+.2f}, max {d.max():+.2f}, min {d.min():+.2f} dB"))
