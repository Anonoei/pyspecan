"""Digital demodulation: the selected signal's symbols as a constellation (dots, a vector diagram, a density, in 3d),
an eye diagram and a symbol table"""
import numpy as np

from ..base import About, plot
from ..frame import (
    BLUE,
    IMAGE,
    LINE,
    RED,
    SCATTER,
    THREE_D,
    YELLOW,
    Axis,
    Frame,
    Image,
    Table,
    TableRow,
    Trace,
)
from ..freq import SETTING_CMAP
from ..reduce import accumulate, density, log_image
from ..settings import Setting
from .common import SETTING_DECAY, DSPPlot, error_summary, eye_points, matched


@plot("Constellation")
class Constellation(DSPPlot):
    """The selected signal's symbols after timing, carrier and gain recovery, over the ideal points"""
    TITLE = "Constellation"
    CATEGORY = "Digital demodulation"
    ABOUT = About(
        data='The analysed signal (the Analysis settings, or a box clicked on the signals marker) shifted'
             ' to 0 Hz, filtered and decimated; its symbol rate, roll-off, timing and carrier recovered '
             '(rpps); the symbols matched filtered and corrected for frequency, phase and gain',
        shows='Symbols (yellow) over the ideal points (red); modulation, rate, Es/N0, EVM and the error '
              'summary',
        use=(
            'Identify a modulation and judge its quality',
            'Spot phase noise (arcs), IQ imbalance (skew), compression (squeezed outer points)',
        ),
        cost=15,
    )
    FEATURES = frozenset({SCATTER})
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("count", "Symbols", "int", default=1000, min=16, max=20000, step=100, group="Display", help="latest symbols shown"),
    )

    def render(self):
        sel, lk, why = self.analyse()
        lim = 1.5
        if lk is None:
            return self.empty([Axis(xmin=-lim, xmax=lim, ymin=-lim, ymax=lim, square=True, xlabel="I", ylabel="Q")], sel, why)
        s = lk.syms[-self.count:]
        lim = max(1.5, 1.2 * float(np.max(np.abs(lk.points)))) # type: ignore
        return Frame([Axis(
            xmin=-lim, xmax=lim, ymin=-lim, ymax=lim, square=True, xlabel="I", ylabel="Q",
            traces=[Trace(s.imag, s.real, color=YELLOW, kind=SCATTER, name="syms"),
                    Trace(lk.points.imag, lk.points.real, color=RED, kind=SCATTER, name="ideal")],
        )], title=self.TITLE, readout=[*self.sel_readout(sel), *self.lock_readout(lk), *error_summary(lk)])


@plot("Vector Diagram")
class VectorDiagram(DSPPlot):
    """The constellation with the path between the symbols: the matched filter's output drawn as a line, so the
    transitions show (a filtered PSK passing near the origin, an offset QPSK that never does, a timing error smearing
    the arrivals)"""
    TITLE = "Vector Diagram"
    CATEGORY = "Digital demodulation"
    ABOUT = About(
        data='The analysed signal (the Analysis settings, or a box clicked on the signals marker) shifted'
             ' to 0 Hz, filtered and decimated; its symbol rate, roll-off, timing and carrier recovered '
             "(rpps); the matched filter's output between the symbols as well",
        shows='The path between symbols as lines, the symbols marked, the ideal points',
        use=('See transitions: through the origin or around it, filtering', 'Spot timing errors (smeared arrivals)'),
        cost=21,
    )
    FEATURES = frozenset({LINE, SCATTER})
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("count", "Symbols", "int", default=200, min=4, max=5000, step=50, group="Display", help="latest symbols drawn"),
        Setting("marks", "Mark symbols", "check", default=True, group="Display", help="mark the symbol instants"),
    )

    def render(self):
        sel, lk, why = self.analyse()
        lim = 1.5
        if lk is None:
            return self.empty([Axis(xmin=-lim, xmax=lim, ymin=-lim, ymax=lim, square=True, xlabel="I", ylabel="Q")], sel, why)
        n = min(self.count, len(lk.syms))
        k0 = len(lk.syms) - n
        t, z = matched(lk, 8)
        on = (t >= k0 - 0.5) & (t <= len(lk.syms) - 0.5)
        path = z[on]
        lim = max(1.5, 1.1 * float(np.max(np.abs(path))) if len(path) else 1.5)
        traces = [Trace(path.imag, path.real, color=BLUE, alpha=0.55, width=1.0, name="path")]
        if self.marks:
            s = lk.syms[k0:]
            traces.append(Trace(s.imag, s.real, color=YELLOW, kind=SCATTER, name="syms"))
        traces.append(Trace(lk.points.imag, lk.points.real, color=RED, kind=SCATTER, name="ideal"))
        return Frame([Axis(xmin=-lim, xmax=lim, ymin=-lim, ymax=lim, square=True, xlabel="I", ylabel="Q", traces=traces)],
                     title=self.TITLE, readout=[*self.sel_readout(sel), *self.lock_readout(lk)])


@plot("Constellation Density")
class ConstellationDensity(DSPPlot):
    """The symbols as a heat map, built up over blocks, under the ideal points: how the symbols spread around each
    point (round for noise, stretched along the circle for phase noise, along the radius for compression) shows where
    a scatter of dots only overlaps"""
    TITLE = "Constellation Density"
    CATEGORY = "Digital demodulation"
    ABOUT = About(
        data='The analysed signal (the Analysis settings, or a box clicked on the signals marker) shifted'
             ' to 0 Hz, filtered and decimated; its symbol rate, roll-off, timing and carrier recovered '
             '(rpps); the symbols binned on an I / Q grid, built up with decay',
        shows='A heat map of the symbols under the ideal points',
        use=(
            'See how each point spreads: round for noise, along the circle for phase noise, along the radius for compression',
            'Tell a few outliers from the bulk',
        ),
        cost=16,
    )
    FEATURES = frozenset({IMAGE, SCATTER})
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("bins", "Bins", "int", default=160, min=32, max=1024, group="Display", help="cells across each axis"),
        Setting("ideal", "Ideal points", "check", default=True, group="Display", help="the ideal points over the density"),
        SETTING_DECAY.with_(default=0.9), SETTING_CMAP.with_(default="hot"),
    )

    def reset(self):
        super().reset()
        self.changed_lock()

    def changed_lock(self):
        self.hist = None

    def changed(self, key):
        if key == "bins":
            self.hist = None

    def render(self):
        sel, lk, why = self.analyse()
        lim = 1.5
        if lk is None:
            return self.empty([Axis(xmin=-lim, xmax=lim, ymin=-lim, ymax=lim, square=True, xlabel="I", ylabel="Q")], sel, why)
        lim = max(1.5, 1.3 * float(np.max(np.abs(lk.points))))
        h = density(lk.syms.imag, lk.syms.real, self.bins, self.bins, (-lim, lim), (-lim, lim)) # type: ignore # row 0: +Q
        self.hist = accumulate(self.hist, h, self.decay) # type: ignore
        traces = [Trace(lk.points.imag, lk.points.real, color=BLUE, kind=SCATTER, name="ideal")] if self.ideal else []
        return Frame([Axis(xmin=-lim, xmax=lim, ymin=-lim, ymax=lim, square=True, xlabel="I", ylabel="Q",
                           image=Image(log_image(self.hist), cmap=self.cmap), traces=traces)], # type: ignore
                     title=self.TITLE, readout=[*self.sel_readout(sel), *self.lock_readout(lk), *error_summary(lk)[:4]])


@plot("3D Constellation")
class Constellation3D(DSPPlot):
    """The selected signal's I and Q against time: the matched filter's path between symbols and the symbols on it, a
    constellation unrolled along the time axis"""
    TITLE = "3D Constellation"
    CATEGORY = "Digital demodulation"
    ABOUT = About(
        data='The analysed signal (the Analysis settings, or a box clicked on the signals marker) shifted'
             ' to 0 Hz, filtered and decimated; its symbol rate, roll-off, timing and carrier recovered '
             "(rpps); the matched filter's output",
        shows='I and Q against time: the path between symbols and the symbols on it. Drag to turn it',
        use=('See the timing of transitions', 'Show how symbols follow each other'),
        cost=20,
    )
    FEATURES = frozenset({LINE, SCATTER, THREE_D})
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("count", "Symbols", "int", default=48, min=4, max=2000, step=8, group="Display", help="latest symbols shown"),
        Setting("path", "Path", "check", default=True, group="Display", help="the waveform between the symbols"),
    )

    def render(self):
        sel, lk, why = self.analyse()
        lim = 1.5
        if lk is None:
            return self.empty([Axis(projection="3d", aspect=(3, 1, 1), xmin=0, xmax=1, ymin=-lim, ymax=lim, zmin=-lim, zmax=lim,
                                    xlabel="Symbols", ylabel="I")], sel, why)
        lim = max(1.5, 1.2 * float(np.max(np.abs(lk.points))))
        n = min(self.count, len(lk.syms))
        k0 = len(lk.syms) - n
        k = np.arange(n, dtype=float) # counted from the first one shown
        s = lk.syms[k0:]
        traces = []
        if self.path:
            t, z = matched(lk, 8)
            on = (t >= k0) & (t <= k0 + n - 1)
            traces.append(Trace(z.real[on], t[on] - k0, z=z.imag[on], color=BLUE, alpha=0.6, width=1.0, name="path"))
        traces.append(Trace(s.real, k, z=s.imag, color=YELLOW, kind=SCATTER, name="syms"))
        return Frame([Axis(
            xmin=float(k[0]), xmax=float(k[-1]), ymin=-lim, ymax=lim, zmin=-lim, zmax=lim, projection="3d", aspect=(3, 1, 1),
            xlabel="Symbols", ylabel="I", traces=traces,
        )], title=self.TITLE, readout=[*self.sel_readout(sel), *self.lock_readout(lk)])


@plot("Eye Diagram")
class EyeDiagram(DSPPlot):
    """The selected signal's matched filter output folded over two symbols, I above Q, as a density"""
    TITLE = "Eye Diagram"
    CATEGORY = "Digital demodulation"
    ABOUT = About(
        data='The analysed signal (the Analysis settings, or a box clicked on the signals marker) shifted'
             ' to 0 Hz, filtered and decimated; its symbol rate, roll-off, timing and carrier recovered '
             "(rpps); the matched filter's output interpolated finer and folded over two symbols",
        shows='I (top) and Q (bottom) as a heat map of how often the waveform passes each point: the '
              'instants at 0, 1 and 2, the eye opening in the middle',
        use=(
            'Judge the noise margin (how open the eye is)',
            'Spot timing jitter (blurred crossings)',
            'See filter problems (closed or lopsided eyes)',
        ),
        cost=30,
    )
    FEATURES = frozenset({IMAGE})
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("cols", "Width", "int", default=128, min=32, max=1024, group="Display", advanced=True, help="cells across two symbols"),
        Setting("rows", "Height", "int", default=96, min=16, max=1024, group="Display", advanced=True, help="cells over the amplitude"),
        SETTING_DECAY, SETTING_CMAP.with_(default="hot"),
    )

    def reset(self):
        super().reset()
        self.changed_lock()

    def changed_lock(self):
        self.hist = None

    def changed(self, key):
        if key in ("cols", "rows"):
            self.hist = None

    def render(self):
        sel, lk, why = self.analyse()
        if lk is None:
            return self.empty([Axis(xmin=0, xmax=2, ymin=-1.5, ymax=1.5, xlabel="Symbols", ylabel=c) for c in ("I", "Q")], sel, why)
        u, z = eye_points(lk, self.cols)
        lim = 1.6 * float(max(np.max(np.abs(lk.points.real)), np.max(np.abs(lk.points.imag)), 0.5))
        rng = [[-lim, lim], [0.0, 2.0]]
        new = np.stack([density(part, u, self.rows, self.cols, rng[0], rng[1]) for part in (z.real, z.imag)])
        self.hist = accumulate(self.hist, new, self.decay) # type: ignore
        axes = [Axis(xmin=0.0, xmax=2.0, ymin=-lim, ymax=lim, xlabel="Symbols", ylabel=name,
                     image=Image(log_image(self.hist[k]), cmap=self.cmap)) for k, name in enumerate(("I", "Q"))]
        return Frame(axes, title=self.TITLE, readout=[*self.sel_readout(sel), *self.lock_readout(lk)[:4]])


@plot("Symbol Table")
class SymbolTable(DSPPlot):
    """The decided symbols: each one's point in the constellation (rpps' point order) in a table, eight to a row, and
    against time. The carrier's phase ambiguity (any of the constellation's symmetric rotations) is not resolved"""
    TITLE = "Symbol Table"
    CATEGORY = "Digital demodulation"
    ABOUT = About(
        data='The analysed signal (the Analysis settings, or a box clicked on the signals marker) shifted'
             ' to 0 Hz, filtered and decimated; its symbol rate, roll-off, timing and carrier recovered '
             '(rpps); each symbol decided to the nearest ideal point',
        shows='The decided points (their index in the constellation), eight to a row, and against time',
        use=('Read out the symbol stream', 'Look for repeating patterns: preambles, idle fill'),
        cost=16,
    )
    FEATURES = frozenset({SCATTER})
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("count", "Symbols", "int", default=128, min=8, max=2048, step=8, group="Display", help="latest symbols listed"),
    )

    def render(self):
        sel, lk, why = self.analyse()
        if lk is None:
            return self.empty([Axis(ylabel="Symbol")], sel, why)
        idx = np.argmin(np.abs(lk.syms[:, None] - lk.points[None, :]), axis=1)
        n = min(self.count, len(idx))
        first = len(idx) - n
        width = max(1, int(np.ceil(np.log2(len(lk.points)) / 4))) # hex digits
        rows = []
        for r in range(0, n, 8):
            chunk = idx[first + r:first + r + 8]
            rows.append(TableRow(str(r), [str(r), *[format(int(v), f"0{width}X") for v in chunk]]))
        k = np.arange(n, dtype=float) # counted from the first one listed
        return Frame([Axis(
            xmin=float(k[0]), xmax=float(k[-1]), ymin=-0.5, ymax=len(lk.points) - 0.5, xlabel="Symbol", ylabel="Point",
            traces=[Trace(idx[first:].astype(float), k, color=YELLOW, kind=SCATTER, name="syms")],
        )], title=self.TITLE, readout=[*self.sel_readout(sel), ("Mod", lk.mod), ("Bits / symbol", f"{np.log2(len(lk.points)):g}")],
            table=Table(["Symbol", *[f"+{c}" for c in range(8)]], rows))
