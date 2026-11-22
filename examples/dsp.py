"""DSP plots (pip install pyspecan[dsp]): find the signals in a block, then lock to one and read its symbols

    python examples/dsp.py

A QPSK signal at 50 kBd, 150 kHz off the center, and an FM carrier. The `signals` marker boxes both on the PSD; the
Constellation locks to the strongest (or the one the "Analysis" globals name: `dsp_freq`, `dsp_bw`, `dsp_mod`,
`dsp_baud`) and reports its modulation, symbol rate and EVM. Without rpps these plots are not registered: the script
says so and stops.
"""
import numpy as np

from pyspecan.obj import Frequency
from pyspecan.plots import HAVE_RPPS, PlotSet, Source, layout

FS = 1e6

def qpsk(n, sps=20, beta=0.35, seed=1):
    """QPSK symbols through a root raised cosine, shaped in frequency, unit power"""
    rng = np.random.default_rng(seed)
    syms = ((rng.integers(0, 2, n // sps + 1) * 2 - 1) + 1j * (rng.integers(0, 2, n // sps + 1) * 2 - 1)) / np.sqrt(2)
    up = np.zeros(len(syms) * sps, complex)
    up[::sps] = syms
    f = np.abs(np.fft.fftfreq(len(up))) * sps
    rc = np.where(f <= (1 - beta) / 2, 1.0,
                  np.where(f <= (1 + beta) / 2, 0.5 * (1 + np.cos(np.pi / beta * (f - (1 - beta) / 2))), 0.0))
    x = np.fft.ifft(np.fft.fft(up) * np.sqrt(rc))[:n]
    return x / np.sqrt(np.mean(np.abs(x) ** 2))

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
    if not HAVE_RPPS:
        print("rpps is not installed (pip install pyspecan[dsp]): the DSP plots are not registered")
        return
    n = int(FS * 0.6)
    t = np.arange(n) / FS
    rng = np.random.default_rng(2)
    x = (qpsk(n) * np.exp(2j * np.pi * 150e3 * t)
         + 0.5 * np.exp(1j * (2 * np.pi * -300e3 * t + 4 * np.sin(2 * np.pi * 1.5e3 * t)))
         + 0.01 * (rng.standard_normal(n) + 1j * rng.standard_normal(n))).astype(np.complex64)

    model = Blocks(x, 50_000)
    source = Source(model)
    plots = PlotSet(source)
    plots.apply(layout.parse_inline(["PSD marker=signals", "Constellation"]))
    plots.set_global("dsp_freq", "150k") # analyse the QPSK one, not the (stronger) FM carrier
    while model.next():
        source.tick()
        frames = plots.update()

    psd, const = (frames[pid] for pid, _ in plots)
    print("signals found:")
    for row in psd.table.rows:
        print("  ", row.cells)
    readout = dict(const.readout) # (label, value) pairs, as the views list them
    print("constellation:", ", ".join(f"{k} {readout[k]}" for k in ("Mod", "Baud", "EVM", "CFO")))
    assert readout["Mod"] == "qpsk" and readout["Baud"] == "50 kBd"

if __name__ == "__main__":
    main()
