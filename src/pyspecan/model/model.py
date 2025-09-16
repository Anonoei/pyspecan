import typing
import numpy as np

from .. import err
from ..config import config, Mode
from ..obj import Frequency
from ..utils.window import WindowLUT
from ..utils import psd as _psd
from ..utils import stft

from .reader import Reader

class Model:
    __slots__ = (
        "mode", "reader", "block_size",
        "f", "_samples", "_psd", "_forward", "_reverse",
        "_Fs", "_cf", "_nfft", "_overlap"
    )
    def __init__(self, path, fmt, nfft, Fs, cf):
        self.reader = Reader(fmt, path)
        self._Fs = Frequency.get(Fs)
        self._cf = Frequency.get(cf)

        self._nfft = int(nfft)

        self._overlap = 0.8 # rt

        if config.MODE == Mode.SWEPT:
            self.block_size = self._nfft
        elif config.MODE == Mode.RT:
            self.block_size = self._nfft*4
        else:
            raise err.UnknownOption(f"Unknown mode specified: {config.MODE}")

        self.f = np.arange(-self._Fs.raw/2, self._Fs.raw/2, self._Fs.raw/self._nfft) + self._cf.raw
        self._samples = np.empty(self._nfft, dtype=np.complex64)
        self._psd = np.empty(self._nfft, dtype=np.float32)

    def show(self, ind=0):
        print(" "*ind + "Reader:")
        self.reader.show(ind+2)

    def reset(self):
        self.reader.reset()

    @property
    def samples(self):
        return self._samples

    def psd(self, vbw=None, win="blackman"):
        if self._samples is None:
            return None
        if self._psd is None:
            if config.MODE == Mode.SWEPT:
                psd = _psd.psd(self._samples, self.Fs.raw, vbw, win)
                self._psd = psd
            elif config.MODE == Mode.RT:
                psd = stft.psd(self._samples, self.nfft, self.overlap, self.Fs.raw, vbw, win)
                self._psd = psd
        return self._psd

    def next(self):
        try:
            samples = self.reader.next(self.block_size)
        except err.Overflow:
            return False
        self._samples = samples
        self._psd = None
        return True

    def prev(self):
        try:
            samples = self.reader.prev(self.block_size)
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

    def get_overlap(self):
        return self._overlap
    def set_overlap(self, overlap):
        if overlap <= 0.0 or overlap > 1.0:
            raise ValueError
        self._overlap = float(overlap)
    overlap = property(get_overlap, set_overlap)
