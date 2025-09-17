import argparse

from .base import Model, define_args

from ..utils import psd as _psd

def args_swept(parser: argparse.ArgumentParser):
    define_args(parser)

class ModelSwept(Model):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.block_size = self._nfft

    def psd(self, vbw=None, win="blackman"): # type: ignore
        if self._samples is None:
            return None
        if self._psd is None:
            psd = _psd.psd(self._samples, self.Fs.raw, vbw, win)
            self._psd = psd
        return self._psd
