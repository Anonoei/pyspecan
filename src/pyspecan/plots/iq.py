"""Time domain plots"""
import numpy as np

from ..utils import ComplexPMF
from .base import About, Plot, plot
from .frame import BLUE, GREEN, IMAGE, LINE, RED, SCATTER, THREE_D, YELLOW, Axis, Frame, Image, Trace
from .freq import SETTING_CMAP
from .reduce import accumulate, density, log_image
from .settings import Setting

SETTING_COUNT = Setting("count", "Samples", "int", default=0, min=0, step=256, hint="0 = fft size", help="samples to plot, 0 for one FFT worth", group="Timebase")

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
    CATEGORY = "Time domain"
    ABOUT = About(
        data="The latest samples (an FFT's worth, or the count set)",
        shows='I and Q against sample index',
        use=('Check the raw samples: clipping, a DC offset, a dead channel',),
        cost=0.01,
    )
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
    CATEGORY = "Time domain"
    ABOUT = About(
        data='The latest samples',
        shows='The IQ trajectory along time in 3D with its I and Q projections. Drag to turn it',
        use=('See phase rotate over time', 'Show a modulation as a helix'),
        cost=0.01,
    )
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
    CATEGORY = "Time domain"
    ABOUT = About(
        data="The samples' I and Q values, their histogram accumulated over time",
        shows='The probability of each value, for I and Q',
        use=('Check amplitude statistics and clipping (spikes at the rails)', 'Compare with Gaussian noise'),
        cost=0.46,
    )

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
    CATEGORY = "Time domain"
    ABOUT = About(
        data='The latest samples, normalized to the largest',
        shows='Q against I as dots, unsynchronized',
        use=('See the shape of the raw samples', 'Check IQ imbalance (an ellipse instead of a circle)'),
        cost=0.01,
    )
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
    CATEGORY = "Time domain"
    ABOUT = About(
        data='Every sample of the block binned on an I / Q grid, built up with decay',
        shows='A heat map of where the samples land in the IQ plane',
        use=(
            "See a modulation's shape without demodulating it",
            'Spot compression (a flattened ring) or a DC offset',
        ),
        cost=0.31,
    )
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
        self.hist = accumulate(self.hist, h, self.decay)
        return Frame([Axis(
            xmin=-a, xmax=a, ymin=-a, ymax=a, square=True, xlabel="I", ylabel="Q",
            image=Image(log_image(self.hist), cmap=self.cmap),
        )], title=self.TITLE, readout=[("Samples", str(len(samps))), ("Peak", f"{peak:.3g}")])
