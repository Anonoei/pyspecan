import typing
import numpy as np

from .. import err
from ..config import config, Mode
from ..obj import Frequency
from ..utils.window import WindowLUT

from .reader import Reader, Format

def define_args(parser):
    parser.add_argument("-f", "--path", default=None, help="file path")
    parser.add_argument("-d", "--fmt", choices=Format.choices(), default=Format.cf32.name, help="data format")

    parser.add_argument("-fs", "--Fs", default=1, type=Frequency.get, help="sample rate")
    parser.add_argument("-cf", "--cf", default=0, type=Frequency.get, help="center frequency")
    parser.add_argument("-n", "--nfft", default=1024, help="FFT size")

class Model:
    __slots__ = (
        "mode", "reader",
        "f", "_samples", "_psd", "_forward", "_reverse",
        "_block_size", "_Fs", "_cf", "_nfft"
    )
    def __init__(self, **kwargs):
        path = kwargs.get("path", None)
        fmt = kwargs.get("fmt", None)
        Fs = kwargs.get("Fs", 1)
        cf = kwargs.get("cf", 1)
        nfft = kwargs.get("nfft", 1024)

        self.reader = Reader(fmt, path)
        self._Fs = Frequency.get(Fs)
        self._cf = Frequency.get(cf)

        self._nfft = int(nfft)

        self.f = np.arange(-self._Fs.raw/2, self._Fs.raw/2, self._Fs.raw/self._nfft) + self._cf.raw
        self._samples = np.empty(self._nfft, dtype=np.complex64)
        self._psd = np.empty(self._nfft, dtype=np.float32)
        self._block_size = 0

    def show(self, ind=0):
        print(" "*ind + "Reader:")
        self.reader.show(ind+2)

    def reset(self):
        self.reader.reset()

    @property
    def samples(self):
        return self._samples

    def psd(self, vbw=None, win="blackman") -> np.ndarray:
        ...

    def next(self):
        try:
            samples = self.reader.next(self._block_size)
        except err.Overflow:
            return False
        self._samples = samples
        self._psd = None
        return True

    def prev(self):
        try:
            samples = self.reader.prev(self._block_size)
        except err.Overflow:
            return False
        self._samples = samples
        self._psd = None
        return True

    def cur_time(self):
        return self.reader.cur_samp/self.Fs

    def tot_time(self):
        return self.reader.max_samp/self.Fs

    def get_fs(self):
        return self._Fs
    def set_fs(self, fs):
        self._Fs = Frequency.get(fs)
    Fs = property(get_fs, set_fs)

    def get_cf(self):
        return self._cf
    def set_cf(self, cf):
        self._cf = Frequency.get(cf)
    cf = property(get_cf, set_cf)

    def get_nfft(self):
        return self._nfft
    def set_nfft(self, nfft):
        self._nfft = int(nfft)
    nfft = property(get_nfft, set_nfft)

    def get_block_size(self):
        return self._block_size
    def set_block_size(self, size):
        self._block_size = size
    block_size = property(get_block_size, set_block_size)
