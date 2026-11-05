import numpy as np

from .base import FreqPlot, rounded
from .psd import PlotConfig

class FFT(FreqPlot):
    TITLE = "FFT"
    FIELDS = [f for f in FreqPlot.FIELDS if f["key"] != "vbw"] + [
        {"key": "show_max", "label": "Max hold", "kind": "check"},
        {"key": "show_min", "label": "Min hold", "kind": "check"},
    ]
    def __init__(self, parent, **kwargs):
        kwargs.setdefault("ref_level", 50)
        kwargs.setdefault("scale_div", 5.0)
        kwargs.setdefault("window", PlotConfig.window)
        super().__init__(parent, **kwargs)
        self.vbw = 0.0
        self.show_min = True
        self.show_max = True
        self.reset()

    def reset(self):
        self.mag_min = None
        self.mag_max = None
        self._auto = None

    def set_show_max(self, v):
        self.show_max = bool(v)
        self.mag_max = None
    def set_show_min(self, v):
        self.show_min = bool(v)
        self.mag_min = None

    def _update(self, samps):
        fft = np.fft.fftshift(np.fft.fft(samps))
        mag = np.abs(fft)
        pha = np.angle(fft)
        ybtm, ytop = self.y_range(mag)
        if self.mag_max is None or len(self.mag_max) != len(mag):
            self.mag_max = np.full(len(mag), -np.inf)
        if self.mag_min is None or len(self.mag_min) != len(mag):
            self.mag_min = np.full(len(mag), np.inf)
        np.maximum(self.mag_max, mag, out=self.mag_max)
        np.minimum(self.mag_min, mag, out=self.mag_min)
        series = []
        if self.show_max:
            series.append({"y": rounded(self.mag_max), "color": "#d9534f"})
        if self.show_min:
            series.append({"y": rounded(self.mag_min), "color": "#5b9bd5"})
        series.append({"y": rounded(mag), "color": "#e6d84a"})
        fmin, fmax = self._freq_range()
        return {"axes": [
            {"xmin": fmin, "xmax": fmax, "xfmt": "freq", "ymin": ybtm, "ymax": ytop, "series": series},
            {"xmin": fmin, "xmax": fmax, "xfmt": "freq", "ymin": -4, "ymax": 4,
             "series": [{"y": rounded(pha), "color": "#5b9bd5"}]},
        ]}
