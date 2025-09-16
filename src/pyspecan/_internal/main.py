import argparse
import importlib
import sys

from .. import err
from ..specan import SpecAn

from ..config import config, Mode, View
from ..model.reader import Format

from ..utils.window import WindowLUT

from ..obj import Frequency

def define_args():
    parser = argparse.ArgumentParser("pyspecan", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-f", "--file", default=None, help="file path")
    parser.add_argument("-d", "--dtype", choices=Format.choices(), default=Format.cf32.name, help="data format")

    parser.add_argument("-fs", "--Fs", default=1, type=Frequency.get, help="sample rate")
    parser.add_argument("-cf", "--cf", default=0, type=Frequency.get, help="center frequency")
    parser.add_argument("-n", "--nfft", default=1024, help="FFT size")

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

    config.MODE = mode
    if args.mon_mem:
        config.MON_MEM = True
    if args.profile:
        config.PROFILE = True

    ctrl_args = importlib.import_module(f".controller.{view.path}", "pyspecan").define_args
    ctrl_args(parser)

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

def main_cli_swept():
    args = define_args().parse_args()
    args.view = View.CUI.name
    args.mode = Mode.SWEPT.name
    SpecAn(**vars(args))

def main_cli_rt():
    args = define_args().parse_args()
    args.view = View.CUI.name
    args.mode = Mode.RT.name
    SpecAn(**vars(args))

def main_gui_swept():
    args = define_args().parse_args()
    args.view = View.tkGUI.name
    args.mode = Mode.SWEPT.name
    SpecAn(**vars(args))

def main_gui_rt():
    args = define_args().parse_args()
    args.view = View.tkGUI.name
    args.mode = Mode.RT.name
    SpecAn(**vars(args))
