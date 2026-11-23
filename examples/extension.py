"""A plot and a marker kind of your own, which every view then lists

    python examples/extension.py

In a package of your own, put these in a module and name it under the "pyspecan.plots" entry point group, so pyspecan
imports it at start:

    [project.entry-points."pyspecan.plots"]
    mypkg = "mypkg.specan_plots"

Here they register by being imported, then render on a block held in memory: any object with the Model's `samples`,
`get_fs`, `get_cf`, `get_nfft` and `get_overlap` can feed a Source.
"""
import numpy as np

from pyspecan.obj import Frequency
from pyspecan.plots import LINE, PLOTS, About, Axis, Frame, Plot, PlotSet, Setting, Source, Trace, layout, plot
from pyspecan.plots.markers import MARKER_KINDS, MarkerKind, Result, marker_kind


@plot("Envelope")
class Envelope(Plot):
    """The block's magnitude against time"""
    TITLE = "Envelope"
    CATEGORY = "Time domain"                         # where the plot picker lists it
    ABOUT = About(data="The latest block", shows="|x| against time, times Gain", use=("See bursts",), cost=0.01)
    FEATURES = frozenset({LINE})                     # what a view must draw to offer it
    SETTINGS = (Setting("gain", "Gain", "number", default=1.0, min=0.0, help="scales the trace"),)

    def render(self):
        x = self.source.samples
        if not len(x):
            return None                              # nothing to draw this block
        y = np.abs(x) * self.gain                    # settings read as attributes
        t = np.arange(len(x)) / self.source.fs
        return Frame([Axis(xmin=0, xmax=t[-1], ymin=0, ymax=float(y.max()) * 1.1, xfmt="time",
                           traces=[Trace(y, t, name="env")])], title=self.TITLE)


@marker_kind("floor")
class Floor(MarkerKind):
    """The noise floor: the median level of the trace"""
    def evaluate(self, ctx, mid, p):
        level = float(np.median(ctx.trace))
        return Result([["", ctx.level_text(level)]])


class Block:
    """One block of samples in memory, as the Model would hold it"""
    def __init__(self, samples, fs):
        self.samples, self.fs = samples, fs
    def get_fs(self): return Frequency.get(self.fs)
    def get_cf(self): return Frequency.get(0)
    def get_nfft(self): return 1024
    def get_overlap(self): return 0.5


def main():
    fs = 1e6
    rng = np.random.default_rng(0)
    burst = np.r_[np.zeros(20000), np.ones(10000), np.zeros(20000)]
    x = (burst * np.exp(2j * np.pi * 50e3 * np.arange(len(burst)) / fs)
         + 0.01 * (rng.standard_normal(len(burst)) + 1j * rng.standard_normal(len(burst)))).astype(np.complex64)

    assert "Envelope" in PLOTS.names() and "floor" in MARKER_KINDS.names()
    source = Source(Block(x, fs))
    plots = PlotSet(source)
    plots.apply(layout.parse_inline(["Envelope gain=2", "PSD marker=floor"]))
    source.tick()
    frames = plots.update()

    env, psd = (frames[pid] for pid, _ in plots)
    peak = env.axes[0].traces[0].y.max()
    print(f"Envelope peak {peak:.2f} (gain 2), PSD floor {psd.table.rows[0].cells[-1]}")
    assert 1.9 < peak < 2.2

if __name__ == "__main__":
    main()
