"""Spectrum measurement math (numpy only, no knowledge of plots or views)

What plots and marker kinds compute their numbers with: `Averager` (trace averaging), `reduce` (detectors: peak,
sample, average...), `find_peaks` / `interp`, `band_power`, `acpr`, `obw`, `xdb_bw`, `CCDF`, `trigger` (the scope's),
`window` / `WindowLUT` with `enbw` and `coherent_gain`, and units (`UNITS`, `rbw`, `scale`, dB conversions). Anything
new that is math on arrays goes here, tested on its own in `tests/test_measure.py`.
"""
from . import trigger
from .average import Averager
from .ccdf import CCDF
from .channel import acpr, band_power, obw, xdb_bw
from .detector import reduce
from .peaks import find_peaks, interp
from .units import UNITS, db_to_lin, lin_to_db, rbw, scale
from .windows import WindowLUT, coherent_gain, enbw, window
