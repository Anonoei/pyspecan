import numpy as np

from .base import FreqPlot

class PlotConfig:
    ref_level = "auto"
    scale_div = 10.0
    vbw = 10.0
    window = "blackman"

class PSD(FreqPlot):
    def __init__(self, parent, **kwargs):
        kwargs.setdefault("ref_level", PlotConfig.ref_level)
        kwargs.setdefault("scale_div", PlotConfig.scale_div)
        kwargs.setdefault("vbw", PlotConfig.vbw)
        kwargs.setdefault("window", PlotConfig.window)
        super().__init__(parent, **kwargs)
        self.show_min = True
        self.show_max = True
        self.psd_min = None
        self.psd_max = None

    def reset(self):
        self.psd_min = None
        self.psd_max = None

    def set_vbw(self, vbw):
        prev = self.vbw
        super().set_vbw(vbw)
        if prev != self.vbw:
            self.reset()

    def set_window(self, window):
        prev = self.window
        super().set_window(window)
        if prev != self.window:
            self.reset()

    def settings(self):
        return {**super().settings(), "show_min": self.show_min, "show_max": self.show_max}

    def _update(self, samps, **kwargs):
        psd = self.calc_psd(samps)
        if self.ref_level == "auto":
            self.ref_level = self._calc_ref_level(psd)
        if self.psd_max is None or len(self.psd_max) != len(psd):
            self.psd_max = np.repeat(-np.inf, len(psd))
            self.psd_min = np.repeat(np.inf, len(psd))
        np.maximum(self.psd_max, psd, out=self.psd_max)
        np.minimum(self.psd_min, psd, out=self.psd_min)
        return {
            "psd": np.round(psd, 2).tolist(),
            "max": np.round(self.psd_max, 2).tolist() if self.show_max else None,
            "min": np.round(self.psd_min, 2).tolist() if self.show_min else None,
            "y_top": self.y_top,
            "y_btm": self.y_btm,
        }
