import argparse
import sys

from .. import err
from ..specan import SpecAn

from ..config import config, View, Sink
from ..model.model import ModelArgs
from ..plots import args_plots, layout_from_kwargs
from ..controller.controller import ControllerArgs

from ..utils import args

def define_args(view: View = View.tkGUI) -> argparse.ArgumentParser:
    """The options that decide which other options exist: the view and the sink"""
    parser = argparse.ArgumentParser("pyspecan", add_help=False)
    args.update_register(parser)
    parser.add_argument("-v", "--view", type=str, default=view.name, choices=View.choices())
    parser.add_argument("-s", "--sink", type=str.upper, default=None, choices=Sink.choices(),
                        help=f"sample source (default: {Sink.FILE.name}, {Sink.LIVE.name} with --list)")
    parser.add_argument("--list", action="store_true", help="list the radios that can be used and exit: those attached here, and with -d tcp://host:5555 those a pysdrlib server hosts")
    mon = args.get_group(parser, "developer toggles")
    mon.add_argument("--mon_mem", action="store_true")
    mon.add_argument("--profile", action="store_true")
    return parser

def build_parser(view: View, sink: Sink, base: argparse.ArgumentParser | None = None) -> argparse.ArgumentParser:
    """The full parser for `view` and `sink`"""
    parser = argparse.ArgumentParser("pyspecan", parents=[base or define_args()],
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    args.update_register(parser)
    ModelArgs(sink, parser)
    ControllerArgs(view, sink, parser)
    args_plots(parser)
    return parser

def _list_radios(device):
    from ..model.sink.live import list_devices
    address = device if device and "://" in device else None
    print("\n".join(list_devices(address)))

def _main(ns: argparse.Namespace):
    if ns.list:
        return _list_radios(getattr(ns, "device", None))
    kwargs = vars(ns)
    try:
        kwargs["layout"] = layout_from_kwargs(kwargs) # fail before any window opens
    except (ValueError, OSError) as e:
        sys.exit(f"pyspecan: layout: {e}")
    kwargs.pop("layout_items", None)
    SpecAn(**kwargs)

def parse_args(argv=None, view: View = View.tkGUI) -> argparse.Namespace:
    base = define_args(view)
    pre, _ = base.parse_known_args(argv)

    v = View.get(pre.view)
    if v == View.NONE:
        raise err.UnknownOption(f"Unknown view {pre.view}")
    if pre.sink is None:
        pre.sink = Sink.LIVE.name if pre.list else Sink.FILE.name # listing is about radios
    s = Sink.get(pre.sink)
    if s == Sink.NONE:
        raise err.UnknownOption(f"Unknown sink: {pre.sink}")

    ns = build_parser(v, s, base).parse_args(argv)
    ns.sink = s.name
    config.MON_MEM = ns.mon_mem
    config.PROFILE = ns.profile
    return ns

def main():
    _main(parse_args())

def main_cui():
    _main(parse_args(view=View.CUI))
