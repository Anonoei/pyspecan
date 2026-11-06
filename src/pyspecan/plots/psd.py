from .base import plot
from .freq import FreqPlot, HoldMixin
from .frame import Axis, Frame, Trace

@plot("PSD")
class PSD(HoldMixin, FreqPlot):
    """Power spectral density: the last frame of the block, the holds see every frame
    (the persistence plot is its realtime view)"""
    TITLE = "PSD"
    SETTINGS = FreqPlot.SETTINGS + HoldMixin.SETTINGS

    def reset(self):
        super().reset()
        self.reset_hold()

    def render(self):
        rows = self.psd_rows("swept")
        if not len(rows):
            return None
        trace = rows[-1]
        btm, top = self.y_range(trace)
        self.hold(rows)
        fmin, fmax = self.source.freq_range()
        return Frame([Axis(
            xmin=fmin, xmax=fmax, xfmt="freq", ymin=btm, ymax=top, offscale=self.offscale(trace, btm, top),
            traces=self.hold_traces() + [Trace(trace, name="psd")],
        )], title=self.TITLE)
