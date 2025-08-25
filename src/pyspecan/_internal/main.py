import argparse

from ..specan import SpecAn

from ..model.reader import Format

def define_args():
    parser = argparse.ArgumentParser("pyspecan")
    parser.add_argument("-f", "--file", default=None, help="file path")
    parser.add_argument("-d", "--dtype", choices=list([v.name for v in Format]), default="cf32", help="data format")

    parser.add_argument("-n", "--nfft", default=1024, help="FFT size")
    parser.add_argument("-fs", "--Fs", default=1, help="sample rate")
    parser.add_argument("-cf", "--cf", default=0, help="center frequency")
    return parser

def main():
    parser = define_args()
    parser.add_argument("-u", "--ui", choices=["c", "g"], default="c")
    args = parser.parse_args()
    SpecAn(args.ui, args.file, args.dtype, args.nfft, args.Fs, args.cf)

def main_cli():
    args = define_args().parse_args()
    SpecAn("c", args.file, args.dtype, args.nfft, args.Fs, args.cf)

def main_gui():
    args = define_args().parse_args()
    SpecAn("g", args.file, args.dtype, args.nfft, args.Fs, args.cf)
