import typing
import numpy as np

from .. import err
from ..config import config, Mode
from ..utils.window import WindowLUT
from ..utils import psd as _psd
from ..utils import stft

from .reader import Reader

class Model:
    __slots__ = (
        "mode", "reader", "block_size",
        "f", "_samples", "_psd", "_forward", "_reverse",
        "Fs", "cf", "nfft", "overlap"
    )
    def __init__(self, path, fmt, nfft, Fs, cf):
        self.reader = Reader(fmt, path)
        self.Fs = float(Fs)
        self.cf = float(cf)

        self.nfft = int(nfft)

        self.overlap = 0.8 # rt

        if config.MODE == Mode.SWEPT:
            self.block_size = self.nfft
        elif config.MODE == Mode.RT:
            self.block_size = self.nfft*4
        else:
            raise err.UnknownOption(f"Unknown mode specified: {config.MODE}")

        self.f = np.arange(-self.Fs/2, self.Fs/2, self.Fs/self.nfft)
        self._samples = np.empty(self.nfft, dtype=np.complex64)
        self._psd = np.empty(self.nfft, dtype=np.float32)

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
                psd = _psd.psd(self._samples, self.Fs, vbw, win)
                self._psd = psd
            elif config.MODE == Mode.RT:
                psd = stft.psd(self._samples, self.nfft, self.overlap, self.Fs, vbw, win)
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

    def set_path(self, path, fmt):
        if path is None:
            return
        self.reader.set_path(path, fmt)

    def cur_time(self):
        return self.reader.cur_samp/self.Fs

    def tot_time(self):
        return self.reader.max_samp/self.Fs
