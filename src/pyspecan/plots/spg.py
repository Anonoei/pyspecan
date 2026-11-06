import numpy as np

from .base import plot
from .freq import FreqPlot, SETTING_CMAP
from .frame import Axis, Frame, Image, IMAGE
from .settings import Setting

class _Spectrogram(FreqPlot):
    """Spectrogram, newest on top. Subclasses pick how the block is framed (FRAMING) and reduced"""
    FEATURES = frozenset({IMAGE})
    FRAMING = "swept"
    SETTINGS = tuple(
        s.with_(reset=True) if s.key in ("ref_level", "scale_div") else s for s in FreqPlot.SETTINGS
    ) + (
        SETTING_CMAP,
        Setting("max_count", "Max count", "int", default=256, min=1, max=4096, reset=True),
    )

    def reset(self):
        super().reset()
        self._clear = True # tell the view to drop its history

    def rows(self) -> np.ndarray:
        """The new rows of this tick (k, nfft), in dB"""
        raise NotImplementedError()

    def render(self):
        rows = self.rows()
        if not len(rows):
            return None
        rows = rows[-self.max_count:]
        btm, top = self.y_range(rows)
        data = (np.clip((rows - btm) / (top - btm), 0.0, 1.0) * 255).astype(np.uint8)
        clear, self._clear = self._clear, False
        fmin, fmax = self.source.freq_range()
        return Frame([Axis(
            xmin=fmin, xmax=fmax, xfmt="freq", ylabel="sweeps",
            image=Image(data, cmap=self.cmap, scroll=True, rows=self.max_count, clear=clear),
        )], title=self.TITLE)

@plot("Spectrogram")
class SPG(_Spectrogram):
    """One row per swept frame of the block"""
    TITLE = "Spectrogram"

    def rows(self):
        return self.psd_rows("swept")

@plot("RT Spectrogram")
class RTSPG(_Spectrogram):
    """One row per block: the mean of its overlapped (realtime) frames"""
    TITLE = "RT Spectrogram"

    def rows(self):
        rows = self.psd_rows("rt")
        return rows.mean(axis=0, keepdims=True) if len(rows) else rows
