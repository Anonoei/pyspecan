import argparse

from ..specan import SpecAn

from ..config import Mode, View
from ..model.reader import Format

from ..utils.window import WindowLUT

def define_args():
    parser = argparse.ArgumentParser("pyspecan")
    ctrl = parser.add_argument_group("Controller")
    ctrl.add_argument("-f", "--file", default=None, help="file path")
    ctrl.add_argument("-d", "--dtype", choices=Format.choices(), default=Format.cf32.name, help="data format")

    ctrl.add_argument("-fs", "--Fs", default=1, help="sample rate")
    ctrl.add_argument("-cf", "--cf", default=0, help="center frequency")
    ctrl.add_argument("-n", "--nfft", default=1024, help="FFT size")

    view = parser.add_argument_group("View")
    view.add_argument("-rl", "--ref_level", default=0.0, help="Ref Level")
    view.add_argument("-sd", "--scale_div", default=10.0, help="Scale/Div")
    view.add_argument("-vb", "--vbw", default=10.0, help="video bandwidth")
    view.add_argument("-w", "--window", default="blackman", choices=[k for k in WindowLUT.keys()])
    return parser

def main():
    parser = define_args()
    parser.add_argument("-m", "--mode", type=str.upper, default=Mode.SWEPT.name, choices=Mode.choices())
    parser.add_argument("-v", "--view", type=str, default=View.tkGUI.name, choices=View.choices())
    args = parser.parse_args()
    SpecAn(**vars(args))

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
