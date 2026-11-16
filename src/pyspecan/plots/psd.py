from .base import plot
from .freq import FreqPlot, HoldMixin, TraceMixin
from .frame import Axis, Frame, Trace

@plot("PSD")
class PSD(TraceMixin, HoldMixin, FreqPlot):
    """Power spectral density: the last frame of the block (averaged when asked), the holds see every frame
    (the persistence plot is its realtime view). Holds, markers and measurements use full resolution rows,
    only the displayed traces go through the detector."""
    TITLE = "PSD"
    SETTINGS = FreqPlot.SETTINGS + HoldMixin.SETTINGS + TraceMixin.SETTINGS

    def reset(self):
        super().reset()
        self.reset_hold()
        self.reset_avg()

    def render(self):
        raw = self.psd_rows("swept", smooth=False)
        if not len(raw):
            return None
        # markers and measurements read the unsmoothed trace, the vbw only shapes what is drawn
        self.last = self.average(raw)
        trace = self.smooth(self.last)
        btm, top = self.y_range(self.last) # the unsmoothed peaks must fit
        self.hold(self.smooth(raw))
        fmin, fmax = self.source.freq_range()
        frame = Frame([Axis(
            xmin=fmin, xmax=fmax, xfmt="freq", ymin=btm, ymax=top, offscale=self.offscale(self.last, btm, top),
            traces=self.shrink(self.hold_traces() + [Trace(trace, name="psd")]),
        )], title=self.TITLE, readout=self.rbw_readout(len(trace)) + self.avg_readout())
        self.apply_markers(frame)
        return frame
