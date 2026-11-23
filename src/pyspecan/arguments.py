"""Command line options, and which part of pyspecan each one belongs to

Every layer registers its own options (`ModelArgs`, `ControllerArgs`, `args_plots`), and gets only
those back: the model (and its sink) never sees a view's options, nor a view the sink's.

    LAYERS = model: the model and its sink
             ui:    the view and its controller (one frontend, they share e.g. --theme)
             plots: the launch layout and the global plot settings
"""
import argparse

from .config import Sink, View
from .logger import LEVELS
from .utils import args

LAYERS = ("model", "ui", "plots")

def define_args(view: View = View.tkGUI) -> argparse.ArgumentParser:
    """The options that decide which other options exist: the view and the sink"""
    parser = argparse.ArgumentParser("pyspecan", add_help=False)
    args.update_register(parser)
    parser.add_argument("-v", "--view", type=View.normalize, default=view.cli, choices=View.choices(),
                        help="frontend, any case, also c (cui), tkgui, w (web)")
    parser.add_argument("-s", "--sink", type=Sink.normalize, default=None, choices=Sink.choices(),
                        help=f"sample source (default: {Sink.FILE.value}, {Sink.LIVE.value} with --list)")
    parser.add_argument("--list", action="store_true", help="list the radios that can be used and exit: those attached here, and with -d radiohost (or --servers) those of pysdrlib servers")
    log = args.get_group(parser, "logging")
    log.add_argument("--log_level", default=None, choices=LEVELS,
                     help="what to log to stderr (default: info, warning with the cui view)")
    log.add_argument("--log_file", default=None, help="also log everything (from trace on) to this file")
    mon = args.get_group(parser, "developer toggles")
    mon.add_argument("--mon_mem", action="store_true")
    mon.add_argument("--profile", action="store_true")
    return parser

def _dests(parser) -> set[str]:
    return {a.dest for a in parser._actions}

def build_parser(view: View, sink: Sink, base: argparse.ArgumentParser | None = None) -> argparse.ArgumentParser:
    """The full parser for `view` and `sink`. `parser.layers` maps each of LAYERS to the dests it owns"""
    from .controller.controller import ControllerArgs
    from .model.model import ModelArgs
    from .plots import args_plots
    parser = argparse.ArgumentParser("pyspecan", parents=[base or define_args()],
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    args.update_register(parser)
    layers: dict[str, set[str]] = {}
    for layer, add in (("model", lambda: ModelArgs(sink, parser)),
                       ("ui", lambda: ControllerArgs(view, sink, parser)),
                       ("plots", lambda: args_plots(parser))):
        before = _dests(parser)
        add()
        layers[layer] = _dests(parser) - before
    parser.layers = layers # type: ignore[attr-defined]
    return parser

TCPIQ_RENAMED = ("host", "port", "listen", "timeout") # now --tcp_<name>, --host/--port are the web view's

def hint(name: str, view: View, sink: Sink) -> str | None:
    """What to use instead of option `name` (a dest or flag without dashes), for options that moved"""
    from .plots import PLOTS
    name = name.lstrip("-").split("=", 1)[0].replace("-", "_")
    if sink == Sink.FILE and name == "d":
        return "-d picks a live radio, the file format is -F/--fmt"
    if sink == Sink.TCPIQ and name in TCPIQ_RENAMED and not (view == View.WEB and name in ("host", "port")):
        return f"the TCP IQ option is --tcp_{name}"
    if sink == Sink.TCPIQ and name in ("F", "fmt"):
        return "the TCP IQ sample format is --tcp_fmt"
    if any(s.key == name for _, cls in PLOTS.items() for s in cls.SETTINGS):
        return f"a per plot setting now: --plot \"PSD {name}=...\" (layout_items=[...] for SpecAn) or a --layout file"
    return None

def _unknown_message(names, view: View, sink: Sink) -> str:
    notes = [f"{n}: {h}" for n in names if (h := hint(n, view, sink))]
    return "; ".join(notes)

def split(view: View, sink: Sink, kwargs: dict) -> dict[str, dict]:
    """`kwargs` by layer, raises TypeError naming any option `view` and `sink` don't have"""
    layers = build_parser(view, sink).layers # type: ignore[attr-defined]
    out = {layer: {k: v for k, v in kwargs.items() if k in layers[layer]} for layer in LAYERS}
    unknown = sorted(set(kwargs) - set().union(*layers.values()))
    if unknown:
        known = ", ".join(sorted(set().union(*layers.values())))
        notes = _unknown_message(unknown, view, sink)
        raise TypeError(f"unknown option(s) for view {view.cli} and sink {sink.value}: {', '.join(unknown)}"
                        + (f" ({notes})" if notes else f" (known: {known})"))
    return out

def parse(parser: argparse.ArgumentParser, argv, view: View, sink: Sink) -> argparse.Namespace:
    """parser.parse_args, with what to use instead of options that moved"""
    ns, extra = parser.parse_known_args(argv)
    if extra:
        notes = _unknown_message([a for a in extra if a.startswith("-")], view, sink)
        parser.error(f"unrecognized arguments: {' '.join(extra)}" + (f"\n  {notes}" if notes else ""))
    return ns
