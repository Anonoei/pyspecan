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

    def raw_rows(self) -> np.ndarray:
        """The new rows of this tick (k, nfft), in dB, before the vbw"""
        raise NotImplementedError()

    def render(self):
        raw = self.raw_rows()
        if not len(raw):
            return None
        raw = raw[-self.max_count:]
        self.last = raw[-1] # what markers measure
        rows = self.smooth(raw)
        btm, top = self.y_range(rows)
        data = (np.clip((rows - btm) / (top - btm), 0.0, 1.0) * 255).astype(np.uint8)
        clear, self._clear = self._clear, False
        fmin, fmax = self.source.freq_range()
        frame = Frame([Axis(
            xmin=fmin, xmax=fmax, xfmt="freq", ylabel="sweeps",
            image=Image(data, cmap=self.cmap, scroll=True, rows=self.max_count, clear=clear),
        )], title=self.TITLE, readout=self.rbw_readout(rows.shape[-1]))
        self.apply_markers(frame, image=True)
        return frame

@plot("Spectrogram")
class SPG(_Spectrogram):
    """One row per refresh: the last swept frame of the block, the trace the PSD plot draws"""
    TITLE = "Spectrogram"

    def raw_rows(self):
        return self.psd_rows("swept", smooth=False)[-1:]

@plot("RT Spectrogram")
class RTSPG(_Spectrogram):
    """One row per block: the mean of its overlapped (realtime) frames"""
    TITLE = "RT Spectrogram"

    def raw_rows(self):
        rows = self.psd_rows("rt", smooth=False)
        return rows.mean(axis=0, keepdims=True) if len(rows) else rows
