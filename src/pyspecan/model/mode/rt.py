import argparse
from ...utils import args

from .mode import Mode, args_mode
from ...utils import stft

class ModeConfig:
    overlap = 0.6
    block_max = 102400

def args_rt(parser: argparse.ArgumentParser):
    mode = args.get_group(parser, "Mode (RT)")
    args_mode(mode)
    mode.add_argument("--overlap", default=ModeConfig.overlap, type=float)
    mode.add_argument("--block_max", default=ModeConfig.block_max, type=int)

class ModeRT(Mode):
    __slots__ = (
        "_overlap", "_block_max"
    )
    def __init__(self, model, **kwargs):
        super().__init__(model)
        self._overlap = kwargs.get("overlap", ModeConfig.overlap)
        self._block_max = kwargs.get("block_max", ModeConfig.block_max)
        self.update_blocksize()

    def update_blocksize(self):
        self._block_size = int(self.model.get_fs() * (self._sweep_time/1000))
        if self._block_size > self._block_max:
            self._block_size = self._block_max
            super().set_sweep_time((self._block_size/self.model.get_fs())*1000)

    def get_overlap(self):
        return self._overlap
    def set_overlap(self, overlap):
        if overlap <= 0.0 or overlap > 1.0:
            raise ValueError
        self._overlap = float(overlap)
    overlap = property(get_overlap, set_overlap)

    def set_sweep_time(self, ts):
        super().set_sweep_time(ts)
        self.update_blocksize()
