from .base import About, plot
from .frame import Axis, Frame, Trace
from .freq import FreqPlot, HoldMixin, RefMixin, TraceMixin


@plot("PSD")
class PSD(RefMixin, TraceMixin, HoldMixin, FreqPlot):
    """Power spectral density: the last frame of the block (averaged when asked), the holds see every frame
    (the persistence plot is its realtime view). Holds, markers and measurements use full resolution rows,
    only the displayed traces go through the detector."""
    TITLE = "PSD"
    CATEGORY = "Spectrum"
    ABOUT = About(
        data='The block cut into frames (FFT size, window), each transformed and scaled to power per Hz '
             '(or dBm, dBFS); averaged over blocks when asked and smoothed by the VBW; max and min holds '
             'over every frame; the detector reduces the bins to the display points',
        shows='Level against frequency across the tuned span: the live trace (yellow), max hold (red), '
              'min hold (blue), a stored reference (grey), markers and their table; with trace math, live'
              ' - ref on an axis of its own',
        use=(
            'Find and measure signals: peak, channel power, ACPR, occupied bandwidth, harmonics, TOI',
            'Compare against a stored reference before and after a change (store ref, trace math)',
            "Check a limit (the limit marker's pass / fail)",
        ),
        cost=1.0,
    )
    SETTINGS = FreqPlot.SETTINGS + HoldMixin.SETTINGS + TraceMixin.SETTINGS + RefMixin.SETTINGS

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
        self.ref_frame(frame, trace)
        self.apply_markers(frame)
        return frame
