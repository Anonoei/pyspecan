"""What a signal is, then its bursts (pip install pyspecan[dsp]): Waveform ID and Bursts on a TDMA signal

    python examples/bursts.py

QPSK bursts at 100 kBd, 50 kHz off the center, one every 5 ms, each with the 48 symbol preamble they share and a
carrier phase of its own. Waveform ID's tests say the power switches on and off and at what period; Bursts acquires
each burst on the preamble and demodulates it, with its carrier offset, EVM, frame and slot.

Both run rpps' analysis in the background (a plot's `job`): a render hands it the newest block and draws the latest
result. A script waits for it (`job.wait()`) before reading the frame; a view just keeps drawing.
"""
import numpy as np

from pyspecan.obj import Frequency
from pyspecan.plots import HAVE_RPPS, PlotSet, Source, layout

FS = 1e6
BLOCK = 50_000

def rrc(sps: int, beta: float = 0.35, span: int = 8) -> np.ndarray:
    """A root raised cosine pulse, `span` symbols each side"""
    t = np.arange(-span * sps, span * sps + 1) / sps
    with np.errstate(divide="ignore", invalid="ignore"):
        h = (np.sin(np.pi * t * (1 - beta)) + 4 * beta * t * np.cos(np.pi * t * (1 + beta))) / (np.pi * t * (1 - (4 * beta * t) ** 2))
    h[t == 0] = 1 - beta + 4 * beta / np.pi
    edge = np.isclose(np.abs(t), 1 / (4 * beta))
    h[edge] = beta / np.sqrt(2) * ((1 + 2 / np.pi) * np.sin(np.pi / (4 * beta)) + (1 - 2 / np.pi) * np.cos(np.pi / (4 * beta)))
    return h / np.sqrt(np.sum(h ** 2))

def tdma(n_bursts: int, period: int = 5000, sps: int = 10, seed: int = 4) -> np.ndarray:
    rng = np.random.default_rng(seed)
    qpsk = np.exp(1j * (np.pi / 4 + np.pi / 2 * np.arange(4)))
    preamble = qpsk[rng.integers(0, 4, 48)]
    x = np.zeros(n_bursts * period, complex)
    for k in range(n_bursts):
        s = np.concatenate((preamble, qpsk[rng.integers(0, 4, 300)]))
        up = np.zeros(len(s) * sps, complex)
        up[::sps] = s
        burst = np.convolve(up, rrc(sps), "same") * np.sqrt(sps) * np.exp(1j * rng.uniform(0, 2 * np.pi))
        x[k * period + 100:k * period + 100 + len(burst)] += burst
    x *= np.exp(2j * np.pi * 50e3 * np.arange(len(x)) / FS)
    return (x + 0.01 * (rng.standard_normal(len(x)) + 1j * rng.standard_normal(len(x)))).astype(np.complex64)

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
    model = Blocks(tdma(20), BLOCK)
    source = Source(model)
    plots = PlotSet(source)
    plots.apply(layout.parse_inline(["Waveform ID", "Bursts"]))
    plots.set_global("dsp_freq", "50k") # the bursts' channel: 50 kHz off the center,
    plots.set_global("dsp_bw", "160k")  # 160 kHz wide
    while model.next():
        source.tick()
        plots.update()
        for _, plot in plots:
            plot.job.wait() # a script waits for the background analysis; a view does not
        frames = plots.update() # the same block again, drawn with the result just made

    ident, bursts = (frames[pid] for pid, _ in plots)
    tests = {row.cells[0]: row.cells[1] for row in ident.table.rows}
    print("waveform:", tests["Bursts"])
    assert "every 5.000 ms" in tests["Bursts"]

    readout = dict(bursts.readout)
    print("bursts:", ", ".join(f"{k} {readout[k]}" for k in ("Bursts", "Mod", "Baud", "Preamble", "Frame", "EVM")))
    for row in bursts.table.rows[:3]:
        print("  ", row.cells)
    assert readout["Mod"] == "qpsk" and readout["Frame"] == "5 ms"

if __name__ == "__main__":
    main()
