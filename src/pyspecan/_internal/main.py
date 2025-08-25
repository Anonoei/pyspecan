import argparse

from ..specan import SpecAn

from ..config import Mode
from ..model.reader import Format

def define_args():
    parser = argparse.ArgumentParser("pyspecan")
    parser.add_argument("-f", "--file", default=None, help="file path")
    parser.add_argument("-d", "--dtype", choices=[v.name for v in Format], default="cf32", help="data format")

    parser.add_argument("-fs", "--Fs", default=1, help="sample rate")
    parser.add_argument("-cf", "--cf", default=0, help="center frequency")
    parser.add_argument("-n", "--nfft", default=1024, help="FFT size")
    return parser

def main():
    parser = define_args()
    parser.add_argument("-m", "--mode", default=Mode.SWEPT.name, choices=[mode.name for mode in Mode])
    parser.add_argument("-u", "--ui", choices=["c", "g"], default="g")
    args = parser.parse_args()
    SpecAn(args.ui, args.mode, args.file, args.dtype, args.nfft, args.Fs, args.cf)

def main_cli_swept():
    args = define_args().parse_args()
    SpecAn("c", Mode.SWEPT.name, args.file, args.dtype, args.nfft, args.Fs, args.cf)

def main_cli_rt():
    args = define_args().parse_args()
    SpecAn("c", Mode.RT.name, args.file, args.dtype, args.nfft, args.Fs, args.cf)

def main_gui_swept():
    args = define_args().parse_args()
    SpecAn("g", Mode.SWEPT.name, args.file, args.dtype, args.nfft, args.Fs, args.cf)

def main_gui_rt():
    args = define_args().parse_args()
    SpecAn("g", Mode.RT.name, args.file, args.dtype, args.nfft, args.Fs, args.cf)
