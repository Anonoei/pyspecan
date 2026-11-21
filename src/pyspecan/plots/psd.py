from .base import About, plot
from .frame import Axis, Frame
from .freq import FreqPlot, RefMixin, TraceMixin


@plot("PSD")
class PSD(RefMixin, TraceMixin, FreqPlot):
    """Power spectral density as an analyzer's traces: each of them clear/write, average, max / min hold, view or
    blank (see TraceMixin), every one sees every frame of the block (the persistence plot is the realtime view).
    Markers and measurements read the marker trace at full resolution, only the drawn traces go through the detector."""
    TITLE = "PSD"
    CATEGORY = "Spectrum"
    ABOUT = About(
        data='The block cut into frames (FFT size, window), each transformed and scaled to power per Hz '
             '(or dBm, dBFS) and smoothed by the VBW; four traces fold every frame in, each its own way '
             '(clear/write, average, max hold, min hold, view, blank); the detector reduces the bins to the display points',
        shows='Level against frequency across the tuned span: trace 1 (yellow, clear/write), 2 (red, max hold), '
              '3 (blue, min hold) and 4 (green, blank) by default, a stored reference (grey), markers and their '
              'table; with trace math, marker trace - ref on an axis of its own',
        use=(
            'Find and measure signals: peak, channel power, ACPR, occupied bandwidth, harmonics, TOI',
            'Average a noisy trace while a max hold catches what comes and goes',
            'Compare against a stored reference before and after a change (store ref, trace math)',
            "Check a limit (the limit marker's pass / fail)",
        ),
        cost=1.0,
    )
    SETTINGS = FreqPlot.SETTINGS + TraceMixin.SETTINGS + RefMixin.SETTINGS

    def reset(self):
        super().reset()
        self.reset_traces()
        self.last_shown = None

    def render(self):
        raw = self.psd_rows("swept", smooth=False)
        if not len(raw):
            return None
        self.fold(raw)
        mk = self.marker_index()
        # markers and measurements read the marker trace unsmoothed (the vbw only shapes what is drawn)
        self.last = self.trace_data(mk)
        self.last_shown = self.trace_shown(mk)
        level = self.last if self.last is not None else raw[-1] # the auto ref level, with the marker trace blank
        btm, top = self.y_range(level) # the unsmoothed peaks must fit
        fmin, fmax = self.source.freq_range()
        frame = Frame([Axis(
            xmin=fmin, xmax=fmax, xfmt="freq", ymin=btm, ymax=top, offscale=self.offscale(level, btm, top),
            traces=self.shrink(self.trace_list()),
        )], title=self.TITLE, readout=self.rbw_readout(raw.shape[-1]) + self.avg_readout())
        if self.last_shown is not None:
            self.ref_frame(frame, self.last_shown)
        self.apply_markers(frame)
        return frame
