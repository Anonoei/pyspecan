"""Toolkit independent plots: what every view (web, tk, console) draws

    from pyspecan.plots import PLOTS, Source, PlotSet

## How a plot works

- `Source` (`plots.source`) is what plots read: the model's current block, and FFT frame `Stream`s cut from it,
  swept (back to back) or realtime (overlapped), carried across blocks and shared between the plots asking for the
  same (mode, nfft, window). `Source.tick(contiguous)` announces a new block; `reset()` forgets carried samples.
- `Plot` (`plots.base`) turns the source into a `Frame` in `update()` (`render()` in subclasses). It declares
  `SETTINGS` (`plots.settings.Setting`: kind, default, limits, scope: its own, its link group's, or global),
  `FEATURES` (what a view must draw to list it: LINE, SCATTER, IMAGE, THREE_D), `CATEGORY` and `ABOUT` (what pickers
  say about it, including its cost in PSDs), and registers with `@plot("Name")`. It never touches a toolkit.
- `Frame` (`plots.frame`) says what to draw (axes, traces, images, surfaces, marker tables, readouts) and nothing
  about how, so the browser, matplotlib and the terminal draw the same frame. `plots.export` writes one as CSV / JSON.
- `FreqPlot` (`plots.freq`) is the base of spectrum plots: traces, detector, averaging, units, and `markers`
  (`plots.markers`: `MarkerKind` subclasses registered with `@marker_kind("name")`: point, peak, delta, channel
  power, ACPR, OBW, harmonics, TOI, limit...).
- `PlotSet` (`plots.plotset`) is a view's live plots: rows, links (plots of a `LINK_DOMAIN` sharing their "link"
  scope settings and markers), the global settings (`GLOBAL_SETTINGS`: calibration, the DSP analysis), and
  `update()`, which renders every enabled plot for the block (honouring each one's "Update every").
- `LayoutSpec` (`plots.layout`) is what a view starts with and saves: rows of `PlotSpec`s from `--plot` / `--row` or
  a JSON file (`layout_from_kwargs`).

Importing this package registers every plot, in the order pickers list them. To add one, write a `Plot` subclass
decorated with `@plot("Name")` in this package and import it below; every view picks it up. Views list the plots whose
FEATURES they can draw (`available`).

## Extensions

Another package can add plots and marker kinds without changing pyspecan. Put them in a module and name it under the
"pyspecan.plots" entry point group (the Extending guide has a runnable example):

    # pyproject.toml of the extension
    [project.entry-points."pyspecan.plots"]
    mypkg = "mypkg.specan_plots"

    # mypkg/specan_plots.py, importing it registers the plots
    from pyspecan.plots import Plot, plot, Frame, Axis, Trace, Setting, LINE

    @plot("Hello")
    class Hello(Plot):
        TITLE = "Hello"
        FEATURES = frozenset({LINE})            # what a view must draw to list it
        SETTINGS = (Setting("gain", "Gain", default=1.0),)
        def render(self):
            ...                                 # read self.source, return a Frame

With rpps installed (pip install pyspecan[dsp]) the DSP plots of `pyspecan.plots.dsp` register too.

Frequency plots that carry markers subclass `FreqPlot`, new marker kinds subclass `MarkerKind`
with `@marker_kind("name")`. Extensions load after the built in plots (so pickers list them
last), in entry point name order. One that fails to import or registers a name already taken
logs a warning (what it registered before failing stays). Set PYSPECAN_NO_EXTENSIONS=1 to load none.
"""
import argparse
import logging
import os
from importlib import metadata

# isort: off
# registration order is the order views list them in (sorting would also let analog's import of scope go first)
from . import psd, spg, pst, fft, iq, scope, measure, analog, timefreq, sweep, markers
# isort: on
from . import layout
from .base import CATEGORIES, PLOTS, About, Plot, available, plot
from .frame import IMAGE, LINE, SCATTER, THREE_D, Axis, Frame, Image, Scroller, Trace
from .freq import FreqPlot
from .layout import LayoutSpec, PlotSpec
from .markers import MARKER_KINDS, MarkerKind, marker_kind
from .plotset import Link, PlotSet
from .settings import GLOBAL_SETTINGS, HAVE_RPPS, Setting
from .source import Source

if HAVE_RPPS: # the DSP plots and the signals marker, see plots.dsp
    from . import dsp

EXTENSION_GROUP = "pyspecan.plots"
_log = logging.getLogger(__name__)
_extensions_loaded = False

def load_extensions() -> list[str]:
    """Import the modules named in the EXTENSION_GROUP entry points, which registers their plots
    and marker kinds. Runs once, returns the names of the entry points that loaded"""
    global _extensions_loaded
    if _extensions_loaded or os.environ.get("PYSPECAN_NO_EXTENSIONS"):
        return []
    _extensions_loaded = True
    loaded = []
    for ep in sorted(metadata.entry_points(group=EXTENSION_GROUP), key=lambda ep: ep.name):
        try:
            ep.load()
        except Exception as e: # pylint: disable=broad-exception-caught
            _log.warning("pyspecan plot extension %r (%s) failed to load: %s", ep.name, ep.value, e)
        else:
            loaded.append(ep.name)
    return loaded

load_extensions()

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
