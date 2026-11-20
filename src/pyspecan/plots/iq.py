"""Time domain plots"""
import numpy as np

from ..utils import ComplexPMF
from .base import Plot, plot
from .frame import Axis, Frame, Image, Trace, YELLOW, BLUE, RED, GREEN, SCATTER, LINE, IMAGE, THREE_D
from .freq import SETTING_CMAP
from .settings import Setting

SETTING_COUNT = Setting("count", "Samples", "int", default=0, min=0, step=256, hint="0 = fft size", help="samples to plot, 0 for one FFT worth", group="Timebase")

def density(y: np.ndarray, x: np.ndarray, rows: int, cols: int, yr: tuple, xr: tuple) -> np.ndarray:
    """(rows, cols) counts of the points (x, y) over the ranges, row 0 at the top (the largest y): np.histogram2d's
    counts by direct integer binning (it binary searches every point, many times slower)"""
    j = np.floor((np.asarray(x, dtype=np.float64) - xr[0]) * (cols / (xr[1] - xr[0]))).astype(np.int64)
    i = np.floor((yr[1] - np.asarray(y, dtype=np.float64)) * (rows / (yr[1] - yr[0]))).astype(np.int64)
    ok = (i >= 0) & (i < rows) & (j >= 0) & (j < cols)
    return np.bincount(i[ok] * cols + j[ok], minlength=rows * cols).reshape(rows, cols).astype(np.float64)

class TimePlot(Plot):
    """Plots of the raw samples"""
    def block(self) -> np.ndarray:
        """The most recent `count` samples of the block"""
        samps = self.source.samples
        n = self.count or self.source.nfft
        return samps[-n:]

@plot("IQ")
class IQ(TimePlot):
    TITLE = "IQ"
    SETTINGS = (SETTING_COUNT,)

    def reset(self):
        self.y_max = 0.0

    def render(self):
        samps = self.block()
        if not len(samps):
            return None
        self.y_max = float(max(self.y_max, np.max(np.abs(samps.real)), np.max(np.abs(samps.imag))))
        x = np.arange(len(samps)) / len(samps)
        return Frame([Axis(
            xmin=0, xmax=1, ymin=-self.y_max, ymax=self.y_max,
            traces=[Trace(samps.real, x, color=YELLOW, name="real"), Trace(samps.imag, x, color=BLUE, name="imag")],
        )], title=self.TITLE)

@plot("IQ 3D")
class IQ3D(TimePlot):
    TITLE = "IQ 3D"
    FEATURES = frozenset({LINE, THREE_D})
    SETTINGS = (SETTING_COUNT,)

    def reset(self):
        self.amp_max = 0.0

    def render(self):
        samps = self.block()
        if not len(samps):
            return None
        self.amp_max = float(max(self.amp_max, np.max(np.abs(samps.real)), np.max(np.abs(samps.imag))))
        x = np.arange(len(samps)) / len(samps)
        r = np.full(len(samps), self.amp_max)
        return Frame([Axis(
            xmin=0, xmax=1, ymin=-self.amp_max, ymax=self.amp_max, zmin=-self.amp_max, zmax=self.amp_max,
            projection="3d", aspect=(3, 1, 1),
            traces=[
                Trace(samps.real, x, z=-r, color=RED, alpha=0.5, width=1, name="i"),
                Trace(r, x, z=samps.imag, color=BLUE, alpha=0.5, width=1, name="q"),
                Trace(samps.real, x, z=samps.imag, color=GREEN, width=3, name="iq"),
            ],
        )], title=self.TITLE)

@plot("PMF")
class PMF(Plot):
    """Probability mass function of the samples' real and imaginary values, accumulated over time"""
    TITLE = "PMF"

    def reset(self):
        self.pmf = ComplexPMF(256)

    def render(self):
        samps = self.source.samples
        if not len(samps):
            return None
        self.pmf.update(samps)
        x, y = self.pmf.x, self.pmf.y # plotted rotated: probability on x, value on y
        return Frame([Axis(
            traces=[Trace(x.real, y.real, color=YELLOW, name="real"), Trace(x.imag, y.imag, color=BLUE, name="imag")],
        )], title=self.TITLE)

@plot("Phasor")
class Phasor(TimePlot):
    TITLE = "Phasor"
    FEATURES = frozenset({SCATTER})
    SETTINGS = (SETTING_COUNT,)

    def render(self):
        samps = self.block()
        if not len(samps):
            return None
        norm = float(np.max(np.abs(samps))) or 1.0
        s = samps / norm
        return Frame([Axis(
            xmin=-1, xmax=1, ymin=-1, ymax=1, square=True,
            traces=[Trace(s.imag, s.real, color=YELLOW, kind=SCATTER, name="phasor")],
        )], title=f"{self.TITLE} (norm {norm:.2f})")

@plot("IQ Density")
class IQDensity(Plot):
    """The constellation as a heat map: how often the samples land on each I / Q cell, built up over refreshes"""
    TITLE = "IQ Density"
    FEATURES = frozenset({IMAGE})
    SETTINGS = (
        Setting("bins", "Bins", "int", default=128, min=16, max=1024, reset=True, help="cells across each axis", group="Display"),
        SETTING_CMAP,
        Setting("decay", "Decay", "number", default=0.5, min=0.0, max=1.0, step=0.05, group="Display",
                help="how much of the earlier refreshes stays each refresh, 0 shows only the latest block"),
    )

    def reset(self):
        self.hist: np.ndarray | None = None
        self.amp = 0.0

    def render(self):
        samps = self.source.samples
        if not len(samps):
            return None
        peak = float(max(np.max(np.abs(samps.real)), np.max(np.abs(samps.imag))))
        if peak > self.amp or self.hist is None: # outgrew the range: start over with headroom
            self.amp, self.hist = (peak * 1.25) or 1.0, None
        a = self.amp
        h = density(samps.imag, samps.real, self.bins, self.bins, (-a, a), (-a, a)) # row 0 is the top: +Q
        self.hist = h if self.hist is None else self.hist * self.decay + h
        top = float(self.hist.max())
        img = np.log1p(self.hist) * (255.0 / np.log1p(top)) if top > 0 else np.zeros_like(self.hist)
        return Frame([Axis(
            xmin=-a, xmax=a, ymin=-a, ymax=a, square=True, xlabel="I", ylabel="Q",
            image=Image(np.rint(img).astype(np.uint8), cmap=self.cmap),
        )], title=self.TITLE, readout=[("Samples", str(len(samps))), ("Peak", f"{peak:.3g}")])
