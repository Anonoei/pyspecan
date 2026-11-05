import numpy as np

from ..utils import matrix
from .base import plot
from .freq import FreqPlot, SETTING_CMAP
from .frame import Axis, Frame, Image, IMAGE
from .settings import Setting, override

@plot("Persistence")
class PST(FreqPlot):
    """Persistence histogram of the block's overlapped frames, hits per frequency / level bin"""
    TITLE = "Persistence"
    FEATURES = frozenset({IMAGE})
    SETTINGS = override(FreqPlot.SETTINGS, vbw={"default": 0.0}) + (
        SETTING_CMAP.with_(default="hot"),
        Setting("x", "Width", "int", default=1001, min=16, max=4096, flags=("--x",), help="histogram x pixels"),
        Setting("y", "Height", "int", default=600, min=16, max=4096, flags=("--y",), help="histogram y pixels"),
    )

    def render(self):
        rows = self.psd_rows("rt")
        if not len(rows):
            return None
        btm, top = self.y_range(rows)
        mat = matrix.cvec(self.x, self.y, rows.T, top, btm)
        peak = np.max(mat)
        data = (np.clip(mat, 0, None) / peak * 255).astype(np.uint8) if peak > 0 else np.zeros(mat.shape, np.uint8)
        fmin, fmax = self.source.freq_range()
        return Frame([Axis(
            xmin=fmin, xmax=fmax, xfmt="freq", ymin=btm, ymax=top, offscale=self.offscale(rows, btm, top),
            image=Image(data[::-1], cmap=self.cmap), # matrix row 0 is the lowest level
        )], title=f"{self.TITLE} - {len(rows)} FFTs")
