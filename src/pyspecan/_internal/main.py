import argparse
import sys

from .. import err
from ..specan import SpecAn

from ..config import config, Mode, View
from ..model.model import ModelArgs
from ..controller.controller import ControllerArgs

def define_args():
    parser = argparse.ArgumentParser("pyspecan", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    mon = parser.add_argument_group("developer toggles")
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
    mode = Mode.get(args.mode)

    if mode == Mode.NONE:
        raise err.UnknownOption(f"Unknown mode {args.mode}")

    view = View.get(args.view)
    if view == View.NONE:
        raise err.UnknownOption(f"Unknown view {args.view}")

    if args.mon_mem:
        config.MON_MEM = True
    if args.profile:
        config.PROFILE = True

    ModelArgs(mode)(parser)
    ControllerArgs(view, mode)(parser)

    args = parser.parse_args()
    if run_help:
        parser.print_help()
        exit()
    return args

def main():
    parser = define_args()
    parser.add_argument("-v", "--view", type=str, default=View.tkGUI.name, choices=View.choices())
    parser.add_argument("-m", "--mode", type=str.upper, default=Mode.SWEPT.name, choices=Mode.choices())
    _main(_process_args(parser))
