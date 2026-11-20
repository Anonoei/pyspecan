import argparse
import sys

from .. import err
from ..arguments import build_parser, define_args, parse
from ..config import config, View, Sink
from ..plots import layout_from_kwargs
from ..specan import SpecAn

def _list_radios(device, servers=None):
    from ..model.sink.live import list_devices, parse_servers
    address = [device] if device and "://" in device else []
    print("\n".join(list_devices(address + parse_servers(servers))))

def _main(ns: argparse.Namespace):
    kwargs = vars(ns)
    for key in ("mon_mem", "profile"):
        kwargs.pop(key)
    if kwargs.pop("list"):
        return _list_radios(kwargs.get("device"), kwargs.get("servers"))
    view, sink = kwargs.pop("view"), kwargs.pop("sink")
    try:
        kwargs["layout"] = layout_from_kwargs(kwargs) # fail before any window opens
    except (ValueError, OSError) as e:
        sys.exit(f"pyspecan: layout: {e}")
    kwargs.pop("layout_items", None)
    SpecAn(view, sink, **kwargs)

def parse_args(argv=None, view: View = View.tkGUI) -> argparse.Namespace:
    base = define_args(view)
    pre, _ = base.parse_known_args(argv)

    v = View.get(pre.view)
    if v == View.NONE:
        raise err.UnknownOption(f"Unknown view {pre.view}")
    if pre.sink is None:
        pre.sink = Sink.LIVE.value if pre.list else Sink.FILE.value # listing is about radios
    s = Sink.get(pre.sink)
    if s == Sink.NONE:
        raise err.UnknownOption(f"Unknown sink: {pre.sink}")

    ns = parse(build_parser(v, s, base), argv, v, s)
    ns.view, ns.sink = v.name, s.name
    config.MON_MEM = ns.mon_mem
    config.PROFILE = ns.profile
    return ns

def main():
    _main(parse_args())

def main_cui():
    _main(parse_args(view=View.CUI))
