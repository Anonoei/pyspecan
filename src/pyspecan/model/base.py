from .. import logger
from ..utils import args
from ..obj import Frequency

from .sink import Sink

class ModelConfig:
    nfft = 1024
    sweep_time = 50.0   # [ms] of samples read per tick
    overlap = 0.6       # realtime frame overlap
    block_max = 1024*1024
    min_fft = 3         # fewest/most realtime frames in one block
    max_fft = 512

def args_model(parser):
    model = args.get_group(parser, "Model")
    model.add_argument("-n", "--nfft", default=ModelConfig.nfft, type=int, help="FFT size")
    model.add_argument("-st", "--sweep_time", default=ModelConfig.sweep_time, type=float, help="[ms] of samples read per tick")
    model.add_argument("--overlap", default=ModelConfig.overlap, type=float, help="realtime frame overlap")
    model.add_argument("--block_max", default=ModelConfig.block_max, type=int, help="most samples read per tick")
    model.add_argument("--min_fft", default=ModelConfig.min_fft, type=int, help="fewest realtime frames per tick")
    model.add_argument("--max_fft", default=ModelConfig.max_fft, type=int, help="most realtime frames per tick")

class Model:
    """Sample source and the parameters that decide how many samples are read per tick

    Every tick reads one block (see get_block_size). Plots cut that block into
    frames themselves, swept plots back to back and realtime plots overlapped,
    so both see every sample.
    """
    def __init__(self, sink, **kwargs):
        self.log = logger.new("model")
        self._nfft = int(kwargs.get("nfft", ModelConfig.nfft))
        self._sweep_time = float(kwargs.get("sweep_time", ModelConfig.sweep_time))
        self._overlap = float(kwargs.get("overlap", ModelConfig.overlap))
        self._block_max = int(kwargs.get("block_max", ModelConfig.block_max))
        self._min_fft = int(kwargs.get("min_fft", ModelConfig.min_fft))
        self._max_fft = int(kwargs.get("max_fft", ModelConfig.max_fft))

        self.sink: Sink = sink(self, **kwargs)
        self.sink.reset()

    def show(self, ind=0):
        print(" "*ind + f"{type(self).__name__} Sink:")
        self.sink.show(ind+2)

    def reset(self):
        self.log.debug("reset")
        self.sink.reset()

    @property
    def samples(self):
        return self.sink.samples

    def get_fs(self) -> Frequency:
        return self.sink.get_fs()
    def set_fs(self, fs):
        self.sink.set_fs(fs)

    def get_cf(self) -> Frequency:
        return self.sink.get_cf()
    def set_cf(self, cf):
        self.sink.set_cf(cf)

    def get_nfft(self):
        return self._nfft
    def set_nfft(self, nfft):
        self.log.debug("set_nfft(%s)", nfft)
        nfft = int(nfft)
        if nfft < 4:
            raise ValueError("nfft must be at least 4")
        self._nfft = nfft

    def get_overlap(self):
        return self._overlap
    def set_overlap(self, overlap):
        overlap = float(overlap)
        if not 0.0 <= overlap < 1.0:
            raise ValueError("overlap must be in [0, 1)")
        self._overlap = overlap

    def get_sweep_time(self):
        """[ms] of samples in one block, after limits"""
        fs = self.sink.get_fs().raw
        return self.get_block_size() / fs * 1000 if fs else self._sweep_time
    def set_sweep_time(self, ts):
        self.log.debug("set_sweep_time(%s)", ts)
        ts = float(ts)
        if ts < 0:
            raise ValueError("sweep time must not be negative")
        self._sweep_time = ts

    def get_sweep_samples(self):
        """Samples the requested sweep time covers, before limits"""
        return int(self.sink.get_fs().raw * (self._sweep_time/1000))

    def get_block_size(self):
        """Samples read per tick

        Covers the sweep time, but holds at least `min_fft` and at most `max_fft`
        realtime frames, and never more than `block_max` samples (one frame at least).
        """
        nfft = self._nfft
        hop = max(1, int(nfft * (1 - self._overlap)))
        hi = max(nfft, min(nfft + (self._max_fft - 1) * hop, self._block_max))
        lo = min(nfft + (self._min_fft - 1) * hop, hi)
        return int(min(max(self.get_sweep_samples(), lo), hi))
