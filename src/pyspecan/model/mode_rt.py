import argparse

from .base import Model, define_args

from ..utils import stft

def args_rt(parser: argparse.ArgumentParser):
    define_args(parser)
    parser.add_argument("--overlap", default=0.8, type=float)
    parser.add_argument("--fftnum", default=4, type=int)

class ModelRT(Model):
    __slots__ = ("_overlap", "_fftnum")
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._overlap = kwargs.get("overlap", 0.8)
        self._fftnum = kwargs.get("fftnum", 4)
        self.update_blocksize()

    def psd(self, vbw=None, win="blackman"): # type: ignore
        if self._samples is None:
            return None
        if self._psd is None:
            psd = stft.psd(self._samples, self.nfft, self.overlap, self.Fs.raw, vbw, win)
            self._psd = psd
        return self._psd

    def update_blocksize(self):
        self._block_size = self._nfft*self._fftnum

    def set_nfft(self, nfft):
        super().set_nfft(nfft)
        self.update_blocksize()

    def get_overlap(self):
        return self._overlap
    def set_overlap(self, overlap):
        if overlap <= 0.0 or overlap > 1.0:
            raise ValueError
        self._overlap = float(overlap)
    overlap = property(get_overlap, set_overlap)

    def get_fftnum(self):
        return self._overlap
    def set_fftnum(self, fftnum):
        self._fftnum = int(fftnum)
        self.update_blocksize()
    fftnum = property(get_fftnum, set_fftnum)
