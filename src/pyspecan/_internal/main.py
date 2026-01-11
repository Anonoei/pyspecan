import argparse
import sys

from .. import err
from ..specan import SpecAn

from ..config import config, View, Mode, Sink
from ..model.model import ModelArgs
from ..controller.controller import ControllerArgs

from ..utils import args

def define_args():
    parser = argparse.ArgumentParser("pyspecan", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    args.update_register(parser)
    # mon = parser.add_argument_group("developer toggles")
    mon = args.get_group(parser, "developer toggles")
    mon.add_argument("--mon_mem", action="store_true")
    mon.add_argument("--profile", action="store_true")
    return parser

def _main(args):
    SpecAn(**vars(args))

def _process_args(parser):
    run_help = False
    if "-h" in sys.argv:
        run_help = True
        sys.argv.pop(sys.argv.index("-h"))
    elif "--help" in sys.argv:
        run_help = True
        sys.argv.pop(sys.argv.index("--help"))
    args, remaining = parser.parse_known_args()

    view = View.get(args.view)
    if view == View.NONE:
        raise err.UnknownOption(f"Unknown view {args.view}")

    mode = Mode.get(args.mode)
    if mode == Mode.NONE:
        raise err.UnknownOption(f"Unknown mode {args.mode}")

    sink = Sink.get(args.sink)
    if sink == Sink.NONE:
        raise err.UnknownOption(f"Unknown sink: {args.sink}")

    if args.mon_mem:
        config.MON_MEM = True
    if args.profile:
        config.PROFILE = True

    ModelArgs(mode, sink, parser)
    ControllerArgs(view, mode, sink, parser)

    args = parser.parse_args()
    if run_help:
        parser.print_help()
        exit()
    return args

def main():
    parser = define_args()
    parser.add_argument("-v", "--view", type=str, default=View.tkGUI.name, choices=View.choices())
    parser.add_argument("-m", "--mode", type=str.upper, default=Mode.SWEPT.name, choices=Mode.choices())
    parser.add_argument("-s", "--sink", type=str.upper, default=Sink.FILE.name, choices=Sink.choices())
    _main(_process_args(parser))
