import typing
import numpy as np

from .. import err
from .. import logger
from ..obj import Frequency

from .mode import Mode
from .sink import Sink

def args_model(parser):
    parser.add_argument("-n", "--nfft", default=1024, help="FFT size")

class Model:
    __slots__ = (
        "log", "mode", "sink",
        "f", "_psd", "_nfft"
    )
    def __init__(self, mode, sink, **kwargs):
        self.log = logger.new("model")
        self._nfft = int(kwargs.get("nfft", 1024))

        self.sink: Sink = sink(self, **kwargs)
        self.mode: Mode = mode(self, **kwargs)
        self.sink.reset()

        self.f = self.update_f()
        self._psd = np.empty(self._nfft, dtype=np.float32)

    def show(self, ind=0):
        print(" "*ind + f"{type(self).__name__} Sink:")
        self.sink.show(ind+2)

    def reset(self):
        self.log.debug("reset")
        self.mode.reset()
        self.sink.reset()

    @property
    def samples(self):
        return self.sink.samples

    def psd(self, vbw=None, win="blackman") -> np.ndarray:
        ...

    def get_fs(self):
        return self.sink.get_fs()
    def set_fs(self, fs):
        self.sink.set_fs(fs)

    def get_cf(self):
        return self.sink.get_cf()
    def set_cf(self, cf):
        self.sink.set_cf(cf)

    def get_nfft(self):
        return self._nfft
    def set_nfft(self, nfft):
        self.log.debug("set_nfft(%s)", nfft)
        self._nfft = int(nfft)
        self.f = self.update_f()
        self._psd = np.empty(self._nfft, dtype=np.float32)

    def get_block_size(self):
        return self.mode.get_block_size()
    def set_block_size(self, size):
        self.mode.set_block_size(size)

    def get_sweep_time(self):
        return self.mode.get_sweep_time()
    def set_sweep_time(self, ts):
        self.mode.set_sweep_time(ts)

    def get_sweep_samples(self):
        return int(self.sink.get_fs() * (self.mode.get_sweep_time()/1000))

    def update_f(self):
        return np.arange(
            -self.sink.get_fs().raw/2,
            self.sink.get_fs().raw/2,
            self.sink.get_fs().raw/self._nfft
        ) + self.sink.get_cf().raw
