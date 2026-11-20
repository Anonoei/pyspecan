"""DSP plots on the optional rpps library (pip install pyspecan[dsp]): a `signals` marker kind that boxes every
signal found on a spectrum, and the plots that analyse the one selected (Constellation, Eye Diagram, Network Analyzer)

Imported by pyspecan.plots only when rpps is installed (settings.HAVE_RPPS); rpps itself is imported when they first run.
"""
# isort: off
from . import analyzer, signals, plots # the signals marker kind before the plots, as they list
# isort: on
from .analyzer import Analyzer, Lock, Selection

__all__ = ["analyzer", "signals", "plots", "Analyzer", "Lock", "Selection"] # importing the modules registers them
