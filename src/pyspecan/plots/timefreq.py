"""Time-frequency plots beyond the spectrogram: the wavelet scalogram"""
import numpy as np

from .base import About, Plot, plot
from .frame import IMAGE, Axis, Frame, Image, fmt_time
from .freq import SETTING_CMAP, fmt_hz, freq_text, hz
from .settings import Setting


@plot("Scalogram")
class Scalogram(Plot):
    """Wavelet scalogram: a continuous wavelet transform (Morlet) of the samples, frequency on a log axis against time.
    Unlike a spectrogram's one window for every frequency, each frequency gets a window a fixed number of its own
    cycles long, so high frequencies are sharp in time and low ones sharp in frequency (constant Q): chirps, pulses
    and transients show both their start and their pitch. Frequencies are offsets from the tuned one, positive,
    negative (lower) or both summed"""
    TITLE = "Scalogram"
    CATEGORY = "Time-frequency"
    ABOUT = About(
        data='The latest samples through a continuous wavelet transform (Morlet, a fixed number of cycles'
             ' per frequency), one short FFT per frequency band',
        shows='Frequency offset on a log axis against time, power as color: sharp in time at high '
              'frequencies, sharp in frequency at low ones',
        use=(
            'Analyse chirps, pulses and transients: when they start and their pitch',
            'Look at activity spanning decades of frequency',
        ),
        cost=16,
    )
    FEATURES = frozenset({IMAGE})
    SETTINGS = (
        Setting("samples", "Samples", "int", default=16384, min=256, max=1 << 20, step=1024, group="Timebase",
                help="latest samples transformed (the time shown)"),
        Setting("fmin", "Lowest freq", "text", default="", coerce=freq_text, hint="fs / 1000", group="Wavelet",
                help="the lowest frequency (offset) shown, the top is half the sample rate"),
        Setting("side", "Side", "select", default="both", options=("both", "upper", "lower"), group="Wavelet",
                help="offsets above the tuned frequency, below it, or both summed"),
        Setting("cycles", "Cycles", "number", default=8.0, min=1.0, max=64.0, step=1, group="Wavelet",
                help="wavelet length in cycles: more is finer in frequency (df / f = 1 / cycles), coarser in time"),
        Setting("rows", "Rows", "int", default=128, min=16, max=1024, group="Display", advanced=True, help="frequencies computed"),
        Setting("cols", "Columns", "int", default=512, min=32, max=4096, group="Display", advanced=True, help="time cells drawn"),
        Setting("dyn_range", "Range (dB)", "number", default=60.0, min=10.0, max=160.0, step=10, group="Display",
                help="levels shown below the strongest"),
        SETTING_CMAP,
    )

    def render(self):
        x = np.asarray(self.source.samples, dtype=np.complex128)[-self.samples:] # type: ignore
        n = len(x)
        if n < 64:
            return None
        fs = self.source.fs or 1.0
        fmax = fs / 2
        fmin = min(max(hz(self.fmin, fs / 1000) if self.fmin else fs / 1000, 2 * fs / n), fmax / 2) # type: ignore
        fc = np.geomspace(fmin, fmax, self.rows) # type: ignore
        X = np.fft.fft(x)
        cols = min(self.cols, n) # type: ignore
        power = np.zeros((len(fc), cols))
        sides = {"both": (1, -1), "upper": (1,), "lower": (-1,)}[self.side] # type: ignore
        df = fs / n
        for k, c in enumerate(fc):
            sigma = c / self.cycles # type: ignore # Morlet: a Gaussian in frequency, width f / cycles
            row = np.zeros(cols)
            for sd in sides:
                # only the wavelet's own band: those bins, moved to baseband (|W| does not change), inverse transformed
                # at a length that just holds them gives |W| at a coarser time step, the columns are coarser still
                lo = int(np.floor((sd * c - 5 * sigma) / df))
                hi = int(np.ceil((sd * c + 5 * sigma) / df))
                k_ = np.arange(lo, hi + 1)
                m = max(cols, 1 << int(np.ceil(np.log2(len(k_)))))
                Y = np.zeros(m, complex)
                np.add.at(Y, k_ % m, X[k_ % n] * np.exp(-0.5 * ((k_ * df - sd * c) / sigma) ** 2))
                w = np.abs(np.fft.ifft(Y) * (m / n)) ** 2 # on m steps across the samples
                e = np.linspace(0, m, cols + 1).astype(int)
                row += np.add.reduceat(w, e[:-1]) / np.diff(e)
            # per Hz of the wavelet's band, so white noise is flat whatever the scale
            power[k] = row / (sigma * np.sqrt(2 * np.pi))
        db = 10 * np.log10(power + 1e-30)
        top = float(db.max())
        rng = self.dyn_range # type: ignore
        img = (np.clip((db - (top - rng)) / rng, 0.0, 1.0) * 255).astype(np.uint8)[::-1] # row 0: the highest frequency
        return Frame([Axis(
            xmin=0.0, xmax=n / fs, xfmt="time", ymin=float(np.log10(fmin)), ymax=float(np.log10(fmax)), yfmt="logfreq",
            xlabel="Time", ylabel="Offset", image=Image(img, cmap=self.cmap), # type: ignore
        )], title=self.TITLE, readout=[
            ("Span", fmt_time(n / fs)), ("Freqs", f"{fmt_hz(fmin)} to {fmt_hz(fmax)} ({self.side})"), # type: ignore
            ("Resolution", f"df/f {1 / self.cycles:.2g}, dt {fmt_time(self.cycles / (2 * np.pi * fmax))} at the top, "
                           f"{fmt_time(self.cycles / (2 * np.pi * fmin))} at the bottom"), # type: ignore
        ])
