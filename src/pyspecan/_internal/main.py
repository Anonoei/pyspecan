import argparse
import sys

from .. import err
from ..specan import SpecAn

from ..config import config, View, Sink
from ..model.model import ModelArgs
from ..plots import args_plots
from ..controller.controller import ControllerArgs

from ..utils import args

def define_args():
    parser = argparse.ArgumentParser("pyspecan", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    args.update_register(parser)
    # mon = parser.add_argument_group("developer toggles")
    mon = args.get_group(parser, "developer toggles")
    mon.add_argument("--mon_mem", action="store_true")
    mon.add_argument("--profile", action="store_true")
    parser.add_argument("--list", action="store_true", help="list the radios that can be used and exit: those attached here, and with -d tcp://host:5555 those a pysdrlib server hosts")
    return parser

def _list_radios(device):
    from ..model.sink.live import list_devices
    address = device if device and "://" in device else None
    print("\n".join(list_devices(address)))

def _main(args):
    if args.list:
        return _list_radios(getattr(args, "device", None))
    SpecAn(**vars(args))

def _process_args(parser):
    run_help = False
    if "-h" in sys.argv:
        run_help = True
        sys.argv.pop(sys.argv.index("-h"))
    elif "--help" in sys.argv:
        run_help = True
        sys.argv.pop(sys.argv.index("--help"))
    if "--list" in sys.argv and not any(a in ("-s", "--sink") or a.startswith("--sink=") for a in sys.argv):
        sys.argv += ["-s", "live"] # listing is about radios, which is what -d means for a live sink
    args, remaining = parser.parse_known_args()

    view = View.get(args.view)
    if view == View.NONE:
        raise err.UnknownOption(f"Unknown view {args.view}")

    sink = Sink.get(args.sink)
    if sink == Sink.NONE:
        raise err.UnknownOption(f"Unknown sink: {args.sink}")

    if args.mon_mem:
        config.MON_MEM = True
    if args.profile:
        config.PROFILE = True

    ModelArgs(sink, parser)
    args_plots(parser)
    ControllerArgs(view, sink, parser)

    args = parser.parse_args()
    if run_help:
        parser.print_help()
        exit()
    return args

def define_args_with_view():
    parser = define_args()
    parser.add_argument("-v", "--view", type=str, default=View.tkGUI.name, choices=View.choices())
    parser.add_argument("-s", "--sink", type=str.upper, default=Sink.FILE.name, choices=Sink.choices())
    return parser

def main():
    _main(_process_args(define_args_with_view()))
