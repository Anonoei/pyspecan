import argparse

from ..specan import SpecAn

from ..config import Mode, View
from ..model.reader import Format

def define_args():
    parser = argparse.ArgumentParser("pyspecan")
    parser.add_argument("-f", "--file", default=None, help="file path")
    parser.add_argument("-d", "--dtype", choices=Format.choices(), default=Format.cf32.name, help="data format")

    parser.add_argument("-fs", "--Fs", default=1, help="sample rate")
    parser.add_argument("-cf", "--cf", default=0, help="center frequency")
    parser.add_argument("-n", "--nfft", default=1024, help="FFT size")
    return parser

def main():
    parser = define_args()
    parser.add_argument("-m", "--mode", default=Mode.SWEPT.name, choices=Mode.choices())
    parser.add_argument("-u", "--ui", default=View.tkGUI.name, choices=View.choices())
    args = parser.parse_args()
    SpecAn(args.ui, args.mode, args.file, args.dtype, args.nfft, args.Fs, args.cf)

def main_cli_swept():
    args = define_args().parse_args()
    SpecAn(View.CUI.name, Mode.SWEPT.name, args.file, args.dtype, args.nfft, args.Fs, args.cf)

def main_cli_rt():
    args = define_args().parse_args()
    SpecAn(View.CUI.name, Mode.RT.name, args.file, args.dtype, args.nfft, args.Fs, args.cf)

def main_gui_swept():
    args = define_args().parse_args()
    SpecAn(View.tkGUI.name, Mode.SWEPT.name, args.file, args.dtype, args.nfft, args.Fs, args.cf)

def main_gui_rt():
    args = define_args().parse_args()
    SpecAn(View.tkGUI.name, Mode.RT.name, args.file, args.dtype, args.nfft, args.Fs, args.cf)
