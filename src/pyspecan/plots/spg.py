import numpy as np

from .base import plot
from .freq import FreqPlot, SETTING_MODE, SETTING_CMAP
from .frame import Axis, Frame, Image, IMAGE
from .settings import Setting

@plot("Spectrogram")
class SPG(FreqPlot):
    """Spectrogram, newest on top

    swept: one row per frame in the block, rt: one row per block (the mean of its frames)
    """
    TITLE = "Spectrogram"
    FEATURES = frozenset({IMAGE})
    SETTINGS = (SETTING_MODE,) + tuple(
        s.with_(reset=True) if s.key in ("ref_level", "scale_div") else s for s in FreqPlot.SETTINGS
    ) + (
        SETTING_CMAP,
        Setting("max_count", "Max count", "int", default=256, min=1, max=4096, reset=True),
    )

    def reset(self):
        super().reset()
        self._clear = True # tell the view to drop its history

    def render(self):
        rows = self.psd_rows()
        if not len(rows):
            return None
        if self.mode == "rt":
            rows = rows.mean(axis=0, keepdims=True)
        rows = rows[-self.max_count:]
        btm, top = self.y_range(rows)
        data = (np.clip((rows - btm) / (top - btm), 0.0, 1.0) * 255).astype(np.uint8)
        clear, self._clear = self._clear, False
        fmin, fmax = self.source.freq_range()
        return Frame([Axis(
            xmin=fmin, xmax=fmax, xfmt="freq", ylabel="sweeps",
            image=Image(data, cmap=self.cmap, scroll=True, rows=self.max_count, clear=clear),
        )], title=self.TITLE)
