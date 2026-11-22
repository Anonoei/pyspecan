"""DSP plots on the optional rpps library (pip install pyspecan[dsp])

A `signals` marker kind that boxes every signal found on a spectrum, analog demodulation (AM, FM, PM, SSB), and the
plots that analyse the one selected:

| Module | Plots |
|---|---|
| `signals` | the `signals` marker kind: every signal found in the block, with width, SNR, duty cycle; click to select |
| `analog` | Analog Demod (AM / FM / PM / USB / LSB on `rpps.wave.demod`) |
| `demod` | Constellation, Eye Diagram, 3D Constellation, Vector Diagram, Constellation Density, Symbol Table |
| `quality` | Error Vector, Error Vector Spectrum |
| `channel` | Network Analyzer, Impulse Response, Cyclic Spectrum |
| `decode` | Decode: a signal through one of rpps' profiles, its messages as a table |

The plots of one view share one `Analyzer` per `Source` (`analyzer.analyzer(source)`, used by `common.DSPPlot`): one signal search a block (`Analyzer.survey`),
the `Selection` (the signal at the "Analysis" globals `dsp_freq` / `dsp_bw`, or the strongest found), its baseband,
and its `Lock` (modulation, symbol rate and symbols, on `rpps.sync.Lock`): found once, followed block by block, and
searched again when it goes stale. So a layout of several DSP plots costs about one search and one lock.

Imported by pyspecan.plots only when rpps is installed (settings.HAVE_RPPS, `PYSPECAN_NO_RPPS=1` hides it); rpps itself
is imported when they first run, so `import pyspecan` stays light. Nothing outside this package imports rpps.
"""
# isort: off
# the signals marker kind, then the plots by category (the order views list them in)
from . import analyzer, signals, common, analog, demod, quality, channel, decode
# isort: on
from .analyzer import Analyzer, Lock, Selection

__all__ = ["analyzer", "signals", "common", "analog", "demod", "quality", "channel", "decode", "Analyzer", "Lock", "Selection"] # importing the modules registers them
