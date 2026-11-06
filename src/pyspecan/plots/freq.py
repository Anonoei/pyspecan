"""Shared pieces of the frequency domain plots"""
import numpy as np

from ..utils.vbw import vbw_rows
from ..utils.window import WindowLUT
from . import colormap
from .base import Plot
from .frame import RED, BLUE, Trace
from .settings import Setting

def _ref_level(value):
    if str(value).strip().lower() in ("", "auto"):
        return "auto"
    return float(value)

SETTING_CMAP = Setting("cmap", "Colors", "select", default="magma", options=tuple(colormap.names()), flags=("--cmap",), help="image color map")

def to_psd(spectra: np.ndarray, fs: float) -> np.ndarray:
    """(k, nfft) complex spectra -> dB/Hz"""
    power = np.abs(spectra)**2 / (spectra.shape[-1] * fs)
    return 10.0 * np.log10(np.maximum(power, 1e-30))

class FreqPlot(Plot):
    """Plots with a frequency axis and a ref level / scale per division"""
    SETTINGS = (
        Setting("ref_level", "Ref level", "text", default="auto", coerce=_ref_level, hint="auto", flags=("-rl", "--ref_level"), help="ref level (number or 'auto')"),
        Setting("scale_div", "Scale / div", "number", default=10.0, min=0.0001, step=1, flags=("-sd", "--scale_div"), help="scale per division"),
        Setting("vbw", "VBW", "number", default=10.0, min=0, step=1, reset=True, flags=("-vb", "--vbw"), help="video bandwidth"),
        Setting("window", "Window", "select", default="blackman", options=tuple(WindowLUT), reset=True, flags=("-w", "--window"), help="FFT window function"),
    )

    def reset(self):
        self._auto = None # resolved level while ref_level is "auto"

    def changed(self, key):
        if key == "ref_level":
            self._auto = None

    def psd_rows(self, mode: str = "swept") -> np.ndarray:
        """(k, nfft) psd of the frames in this tick's block (swept: back to back, rt: overlapped), smoothed by the vbw"""
        spectra = self.source.spectra(mode, self.window)
        psd = to_psd(spectra, self.source.fs)
        if self.vbw > 0 and len(psd):
            psd = vbw_rows(psd, self.vbw)
        return psd

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
