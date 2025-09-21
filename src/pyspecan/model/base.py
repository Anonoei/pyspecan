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
    parser.add_argument("-st", "--sweep_time", default=50.0, help="[ms] fft sweep time")

class Model:
    __slots__ = (
        "mode", "reader",
        "f", "_samples", "_psd", "_forward", "_reverse",
        "_Fs", "_cf", "_nfft",
        "_block_size", "_sweep_time"
    )
    def __init__(self, **kwargs):
        path = kwargs.get("path", None)
        fmt = kwargs.get("fmt", None)
        Fs = kwargs.get("Fs", 1)
        cf = kwargs.get("cf", 1)
        nfft = kwargs.get("nfft", 1024)
        sweep_time = kwargs.get("sweep_time", 50.0)

        self.reader = Reader(fmt, path)
        self._Fs = Frequency.get(Fs)
        self._cf = Frequency.get(cf)

        self._nfft = int(nfft)

        self.f = np.arange(-self._Fs.raw/2, self._Fs.raw/2, self._Fs.raw/self._nfft) + self._cf.raw
        self._samples = np.empty(self._nfft, dtype=np.complex64)
        self._psd = np.empty(self._nfft, dtype=np.float32)
        self._block_size = self._nfft
        self._sweep_time = float(sweep_time)

    def show(self, ind=0):
        print(" "*ind + f"{type(self).__name__} Reader:")
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

    def skip_time(self, s):
        samps = int(self.Fs * s)
        # print(f"Skipping {s:.3f}s, {samps} ({samps/self.reader.max_samp*100:.2f}%)")
        self.reader.cur_samp += samps

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
        self.f = np.arange(-self._Fs.raw/2, self._Fs.raw/2, self._Fs.raw/self._nfft) + self._cf.raw
        self._psd = np.empty(self._nfft, dtype=np.float32)
    nfft = property(get_nfft, set_nfft)

    def get_block_size(self):
        return self._block_size
    def set_block_size(self, size):
        self._block_size = size
        self._samples = np.empty(self._block_size, dtype=np.complex64)
    block_size = property(get_block_size, set_block_size)

    def get_sweep_time(self):
        return self._sweep_time
    def set_sweep_time(self, ts):
        self._sweep_time = ts
    sweep_time = property(get_sweep_time, set_sweep_time)

    def sweep_samples(self):
        return int(self.Fs * (self.sweep_time/1000))
