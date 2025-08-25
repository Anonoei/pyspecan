import typing
import numpy as np

from .. import err
from ..utils.window import WindowLUT
from ..utils import psd as _psd
from ..utils import stft

from .reader import Reader

class Model:
    __slots__ = (
        "reader",
        "f", "_samples", "_psd", "_forward", "_reverse",
        "Fs", "cf", "nfft", "win"
    )
    def __init__(self, path, fmt, nfft, Fs, cf):
        self.reader = Reader(fmt, path)
        self.Fs = float(Fs)
        self.cf = float(cf)
        self.nfft = int(nfft)
        self.win = "blackman"

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
            psd = _psd.psd(self._samples, self.Fs, vbw, win)
            self._psd = psd
        return self._psd

    def next(self):
        try:
            samples = self.reader.next(self.nfft)
        except err.Overflow:
            return False
        self._samples = samples
        self._psd = None
        return True

    def prev(self):
        try:
            samples = self.reader.prev(self.nfft)
        except err.Overflow:
            return False
        self._samples = samples
        self._psd = None
        return True

    def set_path(self, path, fmt):
        self.reader.set_path(path, fmt)

    def cur_time(self):
        return self.reader.cur_samp/self.Fs

    def tot_time(self):
        return self.reader.max_samp/self.Fs
