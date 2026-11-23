"""A gated spectrum and a marker trend: a bursty signal's spectrum without the time it is off, and a channel's power
block by block

    python examples/gated.py

A carrier at 100 kHz that is on 30% of the time, getting louder each block. The PSD free running averages the time
it is off in (and the frames cut by a burst's edges splatter over the span); gated (`trig_mode=gated`) it takes only
the FFT frames that fit inside a burst, and its readout says how many. The Marker Trend keeps its channel marker's
power from every block, so the rise shows as a line against time.
"""
import numpy as np

from pyspecan.obj import Frequency
from pyspecan.plots import PlotSet, Source, layout

FS = 1e6
BLOCK = 50_000

class Blocks:
    """A capture in memory, handed out one block at a time as the Model would"""
    def __init__(self, x, block):
        self.x, self.block, self.pos, self.samples = x, block, 0, x[:0]
    def next(self):
        self.samples, self.pos = self.x[self.pos:self.pos + self.block], self.pos + self.block
        return len(self.samples) == self.block
    def get_fs(self): return Frequency.get(FS)
    def get_cf(self): return Frequency.get(0)
    def get_nfft(self): return 1024
    def get_overlap(self): return 0.5

def main():
    n = BLOCK * 6
    t = np.arange(n)
    rng = np.random.default_rng(0)
    on = (t % 10_000) < 3_000                          # 3 ms on in every 10 ms
    louder = 1 + t // BLOCK                            # each block louder than the last
    x = (on * louder * np.exp(2j * np.pi * 100e3 * t / FS)
         + 1e-3 * (rng.standard_normal(n) + 1j * rng.standard_normal(n))).astype(np.complex64)

    model = Blocks(x, BLOCK)
    source = Source(model)
    plots = PlotSet(source)
    plots.apply(layout.parse_inline([
        "PSD unit=dBFS vbw=0 t1_mode=average avg_count=1000",
        "PSD unit=dBFS vbw=0 t1_mode=average avg_count=1000 trig_mode=gated",
        "Marker Trend unit=dBFS trig_mode=gated marker=channel:freq=100k,bw=20k",
    ]))
    while model.next():
        source.tick()
        frames = plots.update()

    free, gated, trend = (frames[pid] for pid, _ in plots)
    print("gate:", dict(gated.readout)["Gate"], "at", dict(gated.readout)["Gate level"])
    peak = lambda f: float(np.max(next(tr.y for tr in f.axes[0].traces if tr.name == "t1"))) # trace 1: the average
    print(f"averaged peak: free run {peak(free):.1f} dBFS, gated {peak(gated):.1f} dBFS")
    assert peak(gated) > peak(free) + 3 # not diluted by the 70% it is off

    power = next(tr for ax in trend.axes for tr in ax.traces if tr.name == "M1 power")
    print("channel power by block:", ", ".join(f"{v:.1f}" for v in power.y), "dBFS")
    assert len(power.y) == 6 and np.all(np.diff(power.y) > 0)

if __name__ == "__main__":
    main()
