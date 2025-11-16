import argparse

from .base import Model, define_args

from ..utils import psd as _psd

def args_swept(parser: argparse.ArgumentParser):
    define_args(parser)

class ModelSwept(Model):
    def next(self):
        if self.sweep_time <= 0.0:
            return super().next()
        if super().next():
            self.reader.cur_samp += int(self.Fs * (self.sweep_time/1000))
            return True
        return False

    def prev(self):
        if self.sweep_time <= 0.0:
            return super().prev()
        if super().prev():
            self.reader.cur_samp -= int(self.Fs * (self.sweep_time/1000))
            return True
        return False

    def get_nfft(self):
        return super().get_nfft()
    def set_nfft(self, nfft):
        super().set_nfft(nfft)
        self.block_size = self._nfft
    nfft = property(get_nfft, set_nfft)
