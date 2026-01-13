import argparse
from ...utils import args

from .mode import Mode, args_mode
from ...utils import stft

class ModeConfig:
    overlap = 0.6
    block_max = 1024*1024
    min_fft = 3
    max_fft = 512

def args_rt(parser: argparse.ArgumentParser):
    mode = args.get_group(parser, "Mode (RT)")
    args_mode(mode)
    mode.add_argument("--overlap", default=ModeConfig.overlap, type=float)
    mode.add_argument("--block_max", default=ModeConfig.block_max, type=int)
    mode.add_argument("--min_fft", default=ModeConfig.min_fft, type=int)
    mode.add_argument("--max_fft", default=ModeConfig.max_fft, type=int)

class ModeRT(Mode):
    __slots__ = (
        "_overlap", "_block_max",
        "_min_fft", "_max_fft"
    )
    def __init__(self, model, **kwargs):
        super().__init__(model)
        self._overlap = kwargs.get("overlap", ModeConfig.overlap)
        self._block_max = kwargs.get("block_max", ModeConfig.block_max)
        self._min_fft = kwargs.get("min_fft", ModeConfig.min_fft)
        self._max_fft = kwargs.get("max_fft", ModeConfig.max_fft)
        self.update_blocksize()

    def update_blocksize(self):
        _fs = self.model.get_fs()
        _nfft = self.model.get_nfft()
        overlap = 1-self._overlap

        self._block_size = int(_fs * (self._sweep_time/1000))
        num_fft = int(self._block_size/(_nfft*overlap))

        min_fft_b = int(self._min_fft * _nfft * overlap)
        max_fft_b = int(self._max_fft * _nfft * overlap)
        min_fft_ms = (min_fft_b/_fs)*1000
        max_fft_ms = (max_fft_b/_fs)*1000

        if num_fft < self._min_fft:
            self.log.debug("_block_size must be greater than %s (%s), num_fft %s < min_fft %s", min_fft_b, f"{min_fft_ms:.3f}ms", num_fft, self._min_fft)
            self._block_size = min_fft_b
            super().set_sweep_time(min_fft_ms)
        elif num_fft > self._max_fft:
            self.log.debug("_block_size must be less than %s (%s), num_fft %s < min_fft %s", max_fft_b, f"{max_fft_ms:.3f}ms", num_fft, self._max_fft)
            self._block_size = max_fft_b
            super().set_sweep_time(max_fft_ms)

    def get_overlap(self):
        return self._overlap
    def set_overlap(self, overlap):
        if overlap <= 0.0 or overlap > 1.0:
            raise ValueError
        self._overlap = float(overlap)

    def set_sweep_time(self, ts):
        super().set_sweep_time(ts)
        self.update_blocksize()
