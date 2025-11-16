import argparse

from .base import Model, define_args

from ..utils import stft

def args_rt(parser: argparse.ArgumentParser):
    define_args(parser)
    parser.add_argument("--overlap", default=0.6, type=float)
    parser.add_argument("--block_max", default=102400, type=int)

class ModelRT(Model):
    __slots__ = ("_overlap", "_block_max")
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._overlap = kwargs.get("overlap", 0.6)
        self._block_max = kwargs.get("block_max", 102400)
        self.update_blocksize()

    def update_blocksize(self):
        self.block_size = int(self.Fs * (self._sweep_time/1000))
        if self.block_size > self._block_max:
            self.block_size = self._block_max
            super().set_sweep_time((self._block_size/self.Fs)*1000)

    def get_overlap(self):
        return self._overlap
    def set_overlap(self, overlap):
        if overlap <= 0.0 or overlap > 1.0:
            raise ValueError
        self._overlap = float(overlap)
    overlap = property(get_overlap, set_overlap)

    def get_sweep_time(self):
        return super().get_sweep_time()
    def set_sweep_time(self, ts):
        super().set_sweep_time(ts)
        self.update_blocksize()
    sweep_time = property(get_sweep_time, set_sweep_time)

    def get_fs(self):
        return super().get_fs()
    def set_fs(self, fs):
        super().set_fs(fs)
        self.update_blocksize()
    Fs = property(get_fs, set_fs)
