"""Quickstart: a capture on disk, read block by block, drawn as a PSD with a peak marker, without any view

    python examples/quickstart.py

The same plots every view draws (`python -m pyspecan -v web -f tone.cf32 -fs 1M --plot "PSD marker=peak"`), run from
Python: the model reads one block per tick, the Source cuts it into FFT frames, the PlotSet renders each plot into a
Frame. Here the frames are read instead of drawn.
"""
import pathlib
import tempfile

import numpy as np

from pyspecan.config import Sink
from pyspecan.model.model import GetModel
from pyspecan.plots import PlotSet, Source, layout
from pyspecan.plots.export import FORMATS

FS = 1e6     # sample rate [Hz]
TONE = 125e3 # where the tone is [Hz from the center]

def write_capture(path: pathlib.Path, seconds: float = 0.5):
    """A tone in a little noise, as cf32 (two float32 a sample, a GNU Radio .cfile)"""
    rng = np.random.default_rng(1)
    t = np.arange(int(FS * seconds)) / FS
    noise = (rng.standard_normal(len(t)) + 1j * rng.standard_normal(len(t))) * 0.01
    (np.exp(2j * np.pi * TONE * t) + noise).astype(np.complex64).tofile(path)

def main():
    path = pathlib.Path(tempfile.mkdtemp()) / "tone.cf32"
    write_capture(path)

    # the model: the file sink and how many samples a tick reads (the command line's -f, -F, -fs, -cf, -n, -st)
    model = GetModel(Sink.FILE)(path=str(path), fmt="cf32", Fs=FS, cf=0, nfft=1024)
    source = Source(model)
    plots = PlotSet(source)
    plots.apply(layout.parse_inline(["PSD vbw=5 marker=peak", None, "Spectrogram"])) # None: --row

    for _ in range(4): # one tick: read a block, announce it, render every plot
        if not model.sink.next(model.get_block_size()):
            break
        source.tick(model.sink.contiguous)
        frames = plots.update()

    psd_id = next(iter(frames))
    psd = plots.get(psd_id)
    peak = psd.bin_freqs(len(psd.last))[np.argmax(psd.last)]
    print(FORMATS["table"](frames[psd_id]))       # the marker table, as CSV
    print(f"strongest bin at {peak/1e3:.1f} kHz")
    assert abs(peak - TONE) < FS / 1024 * 2, peak # within two bins of the tone

if __name__ == "__main__":
    main()
