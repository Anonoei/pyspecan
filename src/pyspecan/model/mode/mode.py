import numpy as np

from .. import logger

class ModeConfig:
    sweep_time = 50.0

def args_mode(parser):
    parser.add_argument("-st", "--sweep_time", default=ModeConfig.sweep_time, help="[ms] fft sweep time")

class Mode:
    __slots__ = (
        "log", "model",
        "_sweep_time", "_block_size"
    )
    def __init__(self, model, **kwargs):
        self.log = logger.new(f"model.{type(self).__name__}")
        self.model = model
        self._sweep_time: float = kwargs.get("sweep_time", ModeConfig.sweep_time)
        self._block_size: int = self.model._nfft

    def reset(self):
        pass

    def show(self, ind=0):
        raise NotImplementedError()

    def get_block_size(self):
        return self._block_size
    def set_block_size(self, size):
        self.log.debug("set_block_size(%s)", size)
        self._block_size = size
        self.model.sink.reset() # reset model.sink._samples size
    def get_sweep_time(self):
        return self._sweep_time
    def set_sweep_time(self, ts):
        self.log.debug("set_sweep_time(%s)", ts)
        self._sweep_time = ts
