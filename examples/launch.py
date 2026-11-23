"""Launch a view from Python: the same as the command line, options by their dest

    python examples/launch.py                     # the web view on a capture it writes, http://127.0.0.1:8000
    python examples/launch.py tk                  # tkGUI (pip install pyspecan[tk])
    python examples/launch.py cui                 # the console: type `help`

Equivalent to `python -m pyspecan -v web -f tone.cf32 -fs 1M --plot "PSD marker=peak" --plot Spectrogram`. `SpecAn`
returns when the view closes. A LayoutSpec, or the path of a JSON layout, can be given as `layout=`.
"""
import pathlib
import sys
import tempfile

import numpy as np

from pyspecan import SpecAn


def main(view="web"):
    path = pathlib.Path(tempfile.mkdtemp()) / "tone.cf32"
    t = np.arange(1_000_000) / 1e6
    np.exp(2j * np.pi * 125e3 * t).astype(np.complex64).tofile(path)
    SpecAn(view, "file", path=str(path), fmt="cf32", Fs="1M",
           layout_items=["PSD marker=peak", "Spectrogram"]) # --plot items; None between two starts a row

if __name__ == "__main__":
    main(*sys.argv[1:2])
