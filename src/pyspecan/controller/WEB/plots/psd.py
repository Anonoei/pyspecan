import numpy as np

from .base import FreqPlot, rounded

class PlotConfig:
    ref_level = "auto"
    scale_div = 10.0
    vbw = 10.0
    window = "blackman"

class PSD(FreqPlot):
    TITLE = "PSD"
    FIELDS = FreqPlot.FIELDS + [
        {"key": "show_max", "label": "Max hold", "kind": "check"},
        {"key": "show_min", "label": "Min hold", "kind": "check"},
    ]
    def __init__(self, parent, **kwargs):
        for k in ("ref_level", "scale_div", "vbw", "window"):
            kwargs.setdefault(k, getattr(PlotConfig, k))
        super().__init__(parent, **kwargs)
        self.show_min = True
        self.show_max = True
        self.reset()

    def reset(self):
        self.psd_min = None
        self.psd_max = None
        self._auto = None

    def set_show_max(self, v):
        self.show_max = bool(v)
        self.psd_max = None # restart hold when toggled
    def set_show_min(self, v):
        self.show_min = bool(v)
        self.psd_min = None

    def _update(self, samps):
        psd = self.calc_psd(samps)
        ybtm, ytop = self.y_range(psd)
        if self.psd_max is None or len(self.psd_max) != len(psd):
            self.psd_max = np.full(len(psd), -np.inf)
        if self.psd_min is None or len(self.psd_min) != len(psd):
            self.psd_min = np.full(len(psd), np.inf)
        np.maximum(self.psd_max, psd, out=self.psd_max)
        np.minimum(self.psd_min, psd, out=self.psd_min)
        series = []
        if self.show_max:
            series.append({"y": rounded(self.psd_max), "color": "#d9534f"})
        if self.show_min:
            series.append({"y": rounded(self.psd_min), "color": "#5b9bd5"})
        series.append({"y": rounded(psd), "color": "#e6d84a"})
        fmin, fmax = self._freq_range()
        return {"axes": [{"xmin": fmin, "xmax": fmax, "xfmt": "freq", "ymin": ybtm, "ymax": ytop, "series": series}]}
