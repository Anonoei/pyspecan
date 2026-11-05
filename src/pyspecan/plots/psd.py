from .base import plot
from .freq import FreqPlot, HoldMixin, SETTING_MODE
from .frame import Axis, Frame, Trace

@plot("PSD")
class PSD(HoldMixin, FreqPlot):
    """Power spectral density

    swept: the last frame of the block, rt: the mean of its overlapped frames.
    The holds see every frame either way.
    """
    TITLE = "PSD"
    SETTINGS = (SETTING_MODE,) + FreqPlot.SETTINGS + HoldMixin.SETTINGS

    def reset(self):
        super().reset()
        self.reset_hold()

    def render(self):
        rows = self.psd_rows()
        if not len(rows):
            return None
        trace = rows[-1] if self.mode == "swept" else rows.mean(axis=0)
        btm, top = self.y_range(trace)
        self.hold(rows)
        fmin, fmax = self.source.freq_range()
        return Frame([Axis(
            xmin=fmin, xmax=fmax, xfmt="freq", ymin=btm, ymax=top, offscale=self.offscale(trace, btm, top),
            traces=self.hold_traces() + [Trace(trace, name="psd")],
        )], title=self.TITLE)
