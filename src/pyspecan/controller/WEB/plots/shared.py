import numpy as np

from ....utils import ComplexPMF
from .base import _Plot, rounded

class IQ(_Plot):
    TITLE = "IQ"
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.reset()

    def reset(self):
        self.y_max = 0.0

    def _update(self, samps):
        self.y_max = float(max(self.y_max, np.max(np.abs(samps.real)), np.max(np.abs(samps.imag))))
        x = rounded(np.arange(len(samps)) / len(samps), 4)
        return {"axes": [{
            "xmin": 0, "xmax": 1, "xfmt": "num", "ymin": -self.y_max, "ymax": self.y_max,
            "series": [
                {"x": x, "y": rounded(samps.real, 4), "color": "#e6d84a"},
                {"x": x, "y": rounded(samps.imag, 4), "color": "#5b9bd5"},
            ],
        }]}

class PMF(_Plot):
    TITLE = "PMF"
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.reset()

    def reset(self):
        self.pmf = ComplexPMF(256)

    def _update(self, samps):
        self.pmf.update(samps)
        x, y = self.pmf.x, self.pmf.y # plotted rotated: probability on x, value on y, like the tk view
        return {"axes": [{
            "xmin": None, "xmax": None, "xfmt": "num", "ymin": None, "ymax": None,
            "series": [
                {"x": rounded(y.real, 5), "y": rounded(x.real, 4), "color": "#e6d84a"},
                {"x": rounded(y.imag, 5), "y": rounded(x.imag, 4), "color": "#5b9bd5"},
            ],
        }]}

class Phasor(_Plot):
    TITLE = "Phasor"
    def _update(self, samps):
        norm = float(np.max(np.abs(samps)))
        if norm == 0:
            norm = 1.0
        s = samps / norm
        return {"title": f"Phasor (norm {norm:.2f})", "axes": [{
            "xmin": -1, "xmax": 1, "xfmt": "num", "ymin": -1, "ymax": 1, "square": True,
            "series": [{"x": rounded(s.real, 4), "y": rounded(s.imag, 4), "color": "#e6d84a", "kind": "scatter"}],
        }]}
