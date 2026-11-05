import numpy as np

from .base import plot
from .freq import FreqPlot, HoldMixin
from .frame import Axis, Frame, Trace, BLUE
from .settings import override, without

@plot("FFT")
class FFT(HoldMixin, FreqPlot):
    """Magnitude and phase of the block's last swept FFT"""
    TITLE = "FFT"
    SETTINGS = override(without(FreqPlot.SETTINGS, "vbw"),
        ref_level={"default": 50.0}, scale_div={"default": 5.0}, window={"default": "rect"},
    ) + HoldMixin.SETTINGS

    def reset(self):
        super().reset()
        self.reset_hold()

    def render(self):
        spectra = self.source.spectra("swept", self.window)
        if not len(spectra):
            return None
        mags = np.abs(spectra)
        mag = mags[-1]
        btm, top = self.y_range(mag)
        self.hold(mags)
        fmin, fmax = self.source.freq_range()
        return Frame([
            Axis(xmin=fmin, xmax=fmax, xfmt="freq", ymin=btm, ymax=top, offscale=self.offscale(mag, btm, top),
                 traces=self.hold_traces() + [Trace(mag, name="mag")]),
            Axis(xmin=fmin, xmax=fmax, xfmt="freq", ymin=-4, ymax=4, ylabel="phase",
                 traces=[Trace(np.angle(spectra[-1]), color=BLUE, name="phase")]),
        ], title=self.TITLE)
