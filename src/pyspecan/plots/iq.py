"""Time domain plots"""
import numpy as np

from ..utils import ComplexPMF
from .base import Plot, plot
from .frame import Axis, Frame, Trace, YELLOW, BLUE, RED, GREEN, SCATTER, LINE, THREE_D
from .settings import Setting

SETTING_COUNT = Setting("count", "Samples", "int", default=0, min=0, step=256, hint="0 = fft size", help="samples to plot, 0 for one FFT worth")

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
