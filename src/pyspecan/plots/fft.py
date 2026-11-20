import numpy as np

from .base import About, plot
from .frame import BLUE, Axis, Frame, Trace
from .freq import FreqPlot, HoldMixin
from .settings import override, without


@plot("FFT")
class FFT(HoldMixin, FreqPlot):
    """Magnitude and phase of the block's last swept FFT"""
    TITLE = "FFT"
    CATEGORY = "Spectrum"
    ABOUT = About(
        data="The block's last frame (no overlap), transformed: linear magnitude and phase of each bin, "
             'no unit scaling',
        shows='Magnitude (top, linear) and phase in radians (bottom) against frequency, with max and min '
              'holds',
        use=('See raw FFT magnitudes without dB scaling', 'Look at the phase of tones in coherent test signals'),
        cost=0.27,
    )
    MARKERS = False # linear magnitude, markers measure dB traces
    LINK_DOMAIN = None # its levels are not dB, nothing to share with the dB plots
    SETTINGS = override(without(FreqPlot.SETTINGS, "vbw", "unit", "cal_db", "ext_gain"),
        ref_level={"default": 50.0, "scope": "plot"}, scale_div={"default": 5.0, "scope": "plot"},
        window={"default": "rect", "scope": "plot"},
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
