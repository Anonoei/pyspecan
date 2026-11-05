"""Toolkit independent plots

    from pyspecan.plots import PLOTS, Source, PlotSet

Importing this package registers every plot. To add a plot, write a `Plot`
subclass decorated with `@plot("Name")` in this package and import it below, every
view (web, tk, console) picks it up. Views list the plots whose FEATURES they can draw.
"""
import argparse

from .base import Plot, PLOTS, plot, available
from .frame import Frame, Axis, Trace, Image, Scroller
from .plotset import PlotSet
from .settings import Setting
from .source import Source

# registration order is the order views list them in
from . import psd, spg, pst, fft, iq

def plot_args() -> dict[str, Setting]:
    """Settings that can be given on the command line, by key"""
    found: dict[str, Setting] = {}
    for _, cls in PLOTS.items():
        for s in cls.SETTINGS:
            if s.flags and s.key not in found:
                found[s.key] = s
    return found

def args_plots(parser: argparse.ArgumentParser):
    """Add the plot options to `parser`, only values the user gives end up in the kwargs"""
    from ..utils import args
    group = args.get_group(parser, "Plots")
    for key, s in plot_args().items():
        kw = {"dest": key, "default": argparse.SUPPRESS, "help": f"{s.help or s.label}"}
        if s.kind == "select":
            kw["choices"] = list(s.options)
        else:
            kw["type"] = s.parse
        group.add_argument(*s.flags, **kw)

def plot_kwargs(kwargs: dict) -> dict:
    """The plot settings out of a view's kwargs"""
    keys = {s.key for _, cls in PLOTS.items() for s in cls.SETTINGS}
    return {k: v for k, v in kwargs.items() if k in keys}
