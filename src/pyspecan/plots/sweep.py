"""Sweep: a span wider than the radio's sample rate, by stepping its tuning across it (pysdrlib's Device.sweep)"""
import math

import numpy as np

from ..measure import units, windows
from .base import About, plot
from .frame import LINE, Axis, Frame
from .freq import FreqPlot, TraceMixin, fmt_hz, freq_text, hz, to_psd
from .settings import Setting

KEEP = 0.8 # of each step's span is used: the edges roll off in the radio's filters

def plan(start: float, stop: float, fs: float, nfft: int) -> tuple[np.ndarray, int]:
    """(the frequencies to tune to, bins kept around each) so the kept bins tile start..stop on one grid of fs / nfft"""
    if not stop > start:
        raise ValueError(f"the sweep stops ({fmt_hz(stop)}) where it starts ({fmt_hz(start)}) or below")
    keep = max(2, int(nfft * KEEP) // 2 * 2) # even: a step's bins sit symmetric about its center
    step = keep * fs / nfft
    steps = max(1, math.ceil((stop - start) / step))
    return start + step / 2 + step * np.arange(steps), keep

@plot("Sweep")
class Sweep(TraceMixin, FreqPlot):
    """A span wider than the sample rate, swept: the radio is tuned across start..stop in steps of 80% of its sample
    rate, the middle of each step's spectrum kept, and the steps joined into one trace. Needs a live radio this program
    controls; the radio goes back to its center frequency after each sweep"""
    TITLE = "Sweep"
    CATEGORY = "Spectrum"
    FEATURES = frozenset({LINE})
    LINK_DOMAIN = "sweep" # its frequencies are not the tuned span's
    NEEDS_RADIO = True
    ABOUT = About(
        data="The radio retuned across start..stop (pysdrlib's sweep: each step after its retune settled, one with lost "
             "samples captured again); at each step FFT size frames averaged to power per Hz, the middle 80% kept",
        shows="Level against frequency across the whole sweep, as the PSD's traces (clear/write, average, max / min hold), "
              "with markers",
        use=(
            "Survey a band wider than the radio's sample rate",
            "Find where signals are before tuning to one",
            "Max hold across a band to catch what comes and goes",
        ),
        # measured with pysdrlib's sim radio (no retune settling) at the defaults, 7 steps: a real radio's settling adds to
        # it. Raise "Update every" to keep the rest of a layout live
        cost=700.0,
    )
    SETTINGS = FreqPlot.SETTINGS + TraceMixin.SETTINGS + (
        Setting("start", "Start", "text", default="", coerce=freq_text, hint="center - 2.5 x span", group="Sweep",
                reset=True, help="where the sweep starts, e.g. 88M (blank: 2.5 sample rates below the center frequency)"),
        Setting("stop", "Stop", "text", default="", coerce=freq_text, hint="center + 2.5 x span", group="Sweep",
                reset=True, help="where the sweep stops, e.g. 108M (blank: 2.5 sample rates above the center frequency)"),
        Setting("frames", "Frames / step", "int", default=4, min=1, max=1024, group="Sweep",
                help="FFTs averaged at each step: more is smoother, and slower"),
    )

    def reset(self):
        super().reset()
        self.reset_traces()
        self._freqs = None
        self._why = ""

    def span(self) -> tuple[float, float]:
        cf, fs = self.source.cf, self.source.fs
        return hz(self.start, cf - 2.5 * fs), hz(self.stop, cf + 2.5 * fs)

    # the frequency axis is the sweep's, not the tuned span's
    def bin_freqs(self, n: int) -> np.ndarray:
        if self._freqs is not None and len(self._freqs) == n:
            return self._freqs
        lo, hi = self.span()
        return lo + np.arange(n) * ((hi - lo) / max(n, 1))

    def reduced(self, y, points, mode="peak"):
        from ..measure import detector
        n = len(y)
        x, out = detector.reduce(y, points, mode)
        if len(out) >= n:
            return None, out
        f = self.bin_freqs(n)
        return f[0] + x * (self.source.fs / self.source.nfft), out

    def rbw(self, nfft=None) -> float:
        return units.rbw(self.source.fs, self.source.nfft, windows.window(self.window, self.source.nfft))

    def measure(self) -> tuple[np.ndarray, np.ndarray]:
        """One sweep: (frequencies, level in the plot's unit)"""
        sink = self.source.model.sink
        if not hasattr(sink, "sweep"):
            raise ValueError("needs a live radio (-s live)")
        fs, nfft = self.source.fs, self.source.nfft
        start, stop = self.span()
        centers, keep = plan(start, stop, fs, nfft)
        frames = int(self.frames)
        lo = nfft // 2 - keep // 2
        freqs, levels = [], []
        for f, x in sink.sweep(centers, nfft * frames):
            spectra = np.fft.fftshift(np.fft.fft(x.reshape(frames, nfft) * windows.window(self.window, nfft), axis=1), axes=1)
            db = to_psd(spectra, fs, self.window, self.unit, self.cal_db, self.ext_gain)[:, lo:lo + keep] # corrected for the whole window
            levels.append(10 * np.log10(np.mean(10 ** (db / 10), axis=0))) # the frames averaged in power
            freqs.append(f + (np.arange(lo, lo + keep) - nfft // 2) * (fs / nfft))
        freqs, levels = np.concatenate(freqs), np.concatenate(levels)
        inside = (freqs >= start) & (freqs <= stop)
        return freqs[inside], levels[inside]

    def render(self):
        start, stop = self.span()
        try:
            freqs, row = self.measure()
        except Exception as e: # no radio, not ours to tune, a bad span: say so on the plot
            self._why = f"{type(e).__name__}: {e}" if not isinstance(e, ValueError) else str(e)
            return Frame([Axis(xmin=start, xmax=max(stop, start + 1), xfmt="freq")], title=self.TITLE,
                         readout=[("Sweep", self._why)])
        if self._freqs is None or len(self._freqs) != len(freqs) or self._freqs[0] != freqs[0]:
            self.reset_traces() # another grid: what the traces held is of other frequencies
        self._freqs = freqs
        self.fold(row[None, :])
        mk = self.marker_index()
        self.last = self.trace_data(mk)
        level = self.last if self.last is not None else row
        btm, top = self.y_range(level)
        steps = len(plan(start, stop, self.source.fs, self.source.nfft)[0])
        frame = Frame([Axis(
            xmin=start, xmax=stop, xfmt="freq", ymin=btm, ymax=top, offscale=self.offscale(level, btm, top),
            traces=self.shrink(self.trace_list()),
        )], title=self.TITLE, readout=self.rbw_readout() + [("Steps", str(steps))] + self.avg_readout())
        self.apply_markers(frame)
        return frame
