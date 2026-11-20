"""Toolkit independent plots

    from pyspecan.plots import PLOTS, Source, PlotSet

Importing this package registers every plot. To add a plot, write a `Plot`
subclass decorated with `@plot("Name")` in this package and import it below, every
view (web, tk, console) picks it up. Views list the plots whose FEATURES they can draw.
"""
import argparse

from .base import Plot, PLOTS, plot, available
from .frame import Frame, Axis, Trace, Image, Scroller
from .plotset import PlotSet, Link
from .settings import Setting, GLOBAL_SETTINGS
from . import layout
from .layout import LayoutSpec, PlotSpec
from .source import Source

# registration order is the order views list them in
from . import psd, spg, pst, fft, iq, scope, measure, markers

def args_plots(parser: argparse.ArgumentParser):
    """The global plot settings (calibration) and the launch layout"""
    from ..utils import args
    group = args.get_group(parser, "Plots", "plots and their settings, see `pyspecan.plots.layout`")
    for s in GLOBAL_SETTINGS:
        kw = {"dest": s.key, "default": argparse.SUPPRESS, "help": s.help or s.label}
        if s.kind == "check":
            kw["action"] = argparse.BooleanOptionalAction
        elif s.kind == "select":
            kw["choices"] = list(s.options)
        else:
            kw["type"] = s.parse
        group.add_argument(*s.flags, **kw)
    group.add_argument("--plot", dest="layout_items", action="append", metavar="SPEC",
                       help="add a plot to the current row: 'NAME key=value ... [link=NAME] [marker=KIND[:key=value,...]]', "
                            f"NAME is one of {', '.join(PLOTS.names())} (case and spaces don't matter)")
    group.add_argument("--row", dest="layout_items", action="append_const", const=None,
                       help="start a new row for the next --plot")
    group.add_argument("--layout", default=None, metavar="FILE", help="json layout file, as saved from a running view")

def global_kwargs(kwargs: dict) -> dict:
    """The global plot settings out of a view's kwargs"""
    keys = {s.key for s in GLOBAL_SETTINGS}
    return {k: v for k, v in kwargs.items() if k in keys}

def layout_from_kwargs(kwargs: dict) -> LayoutSpec:
    """The validated launch layout: `layout` (a LayoutSpec or json file path) or the `layout_items`
    of --plot/--row, else one PSD. Global flags (--cal_db) override the layout's globals"""
    spec = kwargs.get("layout")
    items = kwargs.get("layout_items")
    if spec is not None and items:
        raise ValueError("give either --layout or --plot/--row, not both")
    if isinstance(spec, LayoutSpec):
        pass
    elif spec is not None:
        spec = layout.load(spec)
    elif items:
        spec = layout.parse_inline(items)
    else:
        spec = layout.default()
    spec.globals = {**spec.globals, **global_kwargs(kwargs)}
    layout.validate(spec)
    return spec
