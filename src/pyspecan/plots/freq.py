"""Shared pieces of the frequency domain plots"""
from dataclasses import replace

import numpy as np

from ..measure import Averager, detector, units, windows
from ..measure.windows import WindowLUT
from ..obj import Frequency
from ..utils.vbw import vbw_rows
from . import colormap
from .base import Plot
from .frame import RED, BLUE, Frame, Marker, Trace
from .settings import Setting

def _ref_level(value):
    if str(value).strip().lower() in ("", "auto"):
        return "auto"
    return float(value)

SETTING_CMAP = Setting("cmap", "Colors", "select", default="magma", options=tuple(colormap.names()), flags=("--cmap",), help="image color map")

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
    SETTINGS = (
        Setting("ref_level", "Ref level", "text", default="auto", coerce=_ref_level, hint="auto", flags=("-rl", "--ref_level"), help="ref level (number or 'auto')"),
        Setting("scale_div", "Scale / div", "number", default=10.0, min=0.0001, step=1, flags=("-sd", "--scale_div"), help="scale per division"),
        Setting("vbw", "VBW", "number", default=10.0, min=0, step=1, reset=True, flags=("-vb", "--vbw"), help="video bandwidth"),
        Setting("window", "Window", "select", default="blackman", options=tuple(WindowLUT), reset=True, flags=("-w", "--window"), help="FFT window function"),
        Setting("unit", "Unit", "select", default="dB/Hz", options=units.UNITS, reset=True, flags=("--unit",), help="level unit"),
        Setting("cal_db", "Cal (dBm @ 0 dBFS)", "number", default=0.0, step=1, reset=True, flags=("--cal_db",), help="dBm reading of a full scale tone, for the dBm units"),
        Setting("ext_gain", "Ext gain (dB)", "number", default=0.0, step=1, reset=True, flags=("--ext_gain",), help="gain ahead of the receiver, removed from dBm readings"),
    )

    def __init__(self, source, **kwargs):
        from .markers import MarkerSet # markers import this module
        self.markers = MarkerSet(self)
        self.last = None
        super().__init__(source, **kwargs)

    def reset(self):
        self._auto = None # resolved level while ref_level is "auto"
        self.last = None

    def changed(self, key):
        if key == "ref_level":
            self._auto = None

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
        levels) a marker is a vertical line"""
        if self.last is None:
            return
        marks, bands, table = self.markers.evaluate(self.last, self.bin_freqs(len(self.last)))
        ax = frame.axes[0]
        ax.markers += [replace(m, y=0.0, kind="vline") if image and m.kind == "point" else m for m in marks]
        ax.bands += bands
        frame.table = table

    def resolve_ref(self, values) -> float:
        """The numeric ref level, "auto" is resolved from the first data seen"""
        if self.ref_level != "auto":
            return self.ref_level
        if self._auto is None:
            vmax = float(np.nanmax(values)) if np.isfinite(values).any() else 0.0
            self._auto = int(vmax * 0.9) if vmax < 0 else int(vmax * 1.1)
        return self._auto

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
        Setting("show_max", "Max hold", "check", default=True),
        Setting("show_min", "Min hold", "check", default=True),
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


class TraceMixin:
    """Averaging and the display detector, for the plots that show a trace"""
    SETTINGS = (
        Setting("avg", "Average", "select", default="off", options=("off", "power", "log", "exp"), flags=("--avg",), help="trace averaging"),
        Setting("avg_count", "Avg count", "int", default=10, min=1, max=10000, flags=("--avg_count",), help="traces averaged"),
        Setting("detector", "Detector", "select", default="peak", options=detector.MODES, flags=("--detector",), help="how bins are reduced to display points"),
        Setting("points", "Points", "int", default=1001, min=0, max=65536, step=100, hint="0 = all bins", flags=("--points",), help="display points, 0 for every bin"),
    )

    def reset_avg(self):
        self._avg = Averager(self.avg, self.avg_count) # type: ignore

    def changed(self, key):
        super().changed(key) # type: ignore
        if key in ("avg", "avg_count"):
            self.reset_avg()

    def average(self, rows: np.ndarray) -> np.ndarray:
        """Fold the block's rows into the average, returns the trace to show (full resolution)"""
        return self._avg.update(rows)

    def shrink(self, traces: list[Trace]) -> list[Trace]:
        """Pass traces through the detector, only what is displayed is reduced"""
        for t in traces:
            if t.x is None:
                _, t.y = detector.reduce(t.y, self.points, self.detector) # type: ignore
        return traces

    def avg_readout(self) -> list[tuple[str, str]]:
        if self.avg == "off" or self.avg_count <= 1: # type: ignore
            return []
        return [("Avg", f"{self._avg.n}/{self.avg_count} ({self.avg})")] # type: ignore
