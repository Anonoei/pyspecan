"""DSP plots on the optional rpps library (pip install pyspecan[dsp]): a `signals` marker kind that boxes every
signal found on a spectrum, and the plots that analyse the one selected: demod (constellations, eye diagram, symbol
table), quality (error vector and its spectrum), channel (network analyzer, impulse response, cyclic spectrum)

Imported by pyspecan.plots only when rpps is installed (settings.HAVE_RPPS); rpps itself is imported when they first run.
"""
# isort: off
# the signals marker kind, then the plots by category (the order views list them in)
from . import analyzer, signals, common, demod, quality, channel
# isort: on
from .analyzer import Analyzer, Lock, Selection

__all__ = ["analyzer", "signals", "common", "demod", "quality", "channel", "Analyzer", "Lock", "Selection"] # importing the modules registers them
