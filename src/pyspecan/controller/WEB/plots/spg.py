import base64

import numpy as np

from .base import FreqPlot
from .psd import PlotConfig

class SPG(FreqPlot):
    TITLE = "Spectrogram"
    FIELDS = FreqPlot.FIELDS + [
        {"key": "max_count", "label": "Max count", "kind": "number", "min": 1, "step": 1},
    ]
    def __init__(self, parent, **kwargs):
        for k in ("ref_level", "scale_div", "vbw", "window"):
            kwargs.setdefault(k, getattr(PlotConfig, k))
        super().__init__(parent, **kwargs)
        self.max_count = 256
        self.reset()

    def reset(self):
        self._auto = None
        self._clear = True # tell the browser to drop its history

    def set_max_count(self, count):
        count = int(count)
        if not 1 <= count <= 4096:
            raise ValueError("max count must be 1-4096")
        self.max_count = count
        self.reset()

    def _update(self, samps):
        psd = self.calc_psd(samps)
        ybtm, ytop = self.y_range(psd)
        row = np.clip((psd - ybtm) / (ytop - ybtm), 0.0, 1.0)
        row = (row * 255).astype(np.uint8)
        clear, self._clear = self._clear, False
        fmin, fmax = self._freq_range()
        return {"axes": [{
            "xmin": fmin, "xmax": fmax, "xfmt": "freq", "ymin": None, "ymax": None,
            "image": {"row": base64.b64encode(row.tobytes()).decode(), "rows": self.max_count, "clear": clear},
        }]}
