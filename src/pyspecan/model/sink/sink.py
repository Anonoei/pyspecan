
import math

import numpy as np

from ...obj import Frequency
from .. import logger


class SinkConfig:
    Fs = 1
    cf = 0

def args_sink(parser):
    parser.add_argument("-fs", "--Fs", default=SinkConfig.Fs, type="frequency", help="sample rate")
    parser.add_argument("-cf", "--cf", default=SinkConfig.cf, type="frequency", help="center frequency")

class Sink:
    SEEKABLE = False # can jump around in the stream (files)
    __slots__ = (
        "log", "model",
        "_samples", "_cf", "_Fs", "contiguous", "block_index", "block_time"
    )
    def __init__(self, model, **kwargs):
        self.log = logger.new(f"model.{type(self).__name__}")
        self.model = model
        self.contiguous = True # the last block read follows the one before it, nothing lost or skipped in between
        self.block_index = None # the stream index of the last block's first sample (None: not known)
        self.block_time = None  # its time [s, wall clock or a file's own], None when not known
        self._cf: Frequency = Frequency.get(kwargs.get("cf", SinkConfig.cf))
        self._Fs: Frequency = self._valid_fs(Frequency.get(kwargs.get("Fs", SinkConfig.Fs)))
        self._samples = np.empty((), dtype=np.complex64)

    def reset(self):
        self._samples = np.empty(self.model.get_block_size(), dtype=np.complex64)

    @property
    def samples(self):
        return self._samples

    def show(self, ind=0):
        raise NotImplementedError()

    def close(self):
        """Let go of the source (a device); nothing to do by default"""

    def status(self) -> dict | None:
        """What the views show about the source of live samples (None: a file)"""
        return None

    def stream_status(self) -> dict | None:
        """A network stream's state, every frame (None: not a stream): who sends, the rate samples arrive at"""
        return None

    def measured_rate(self) -> float | None:
        """The rate samples arrive at, when the source measures it (a network stream), None otherwise or not yet"""
        return None

    def live_status(self) -> dict | None:
        """The part of status() that changes block to block, cheap enough for every frame (None: a file)"""
        return None

    def take_retuned(self) -> bool:
        """Did the source change its tuning by itself"""
        return False

    def ready(self) -> bool:
        """Can samples be read, e.g. a file is selected or a device is open"""
        raise NotImplementedError()

    @staticmethod
    def _valid_fs(fs: Frequency) -> Frequency:
        """A sample rate has to be a positive number, everything (times, RBW, block sizes) divides by it"""
        if not math.isfinite(fs.raw) or fs.raw <= 0:
            raise ValueError(f"sample rate must be greater than 0, got {fs}")
        return fs

    def set_fs(self, fs):
        self.log.debug("set_fs(%s)", fs)
        if isinstance(fs, str):
            fs = Frequency.get(fs).raw
        self._valid_fs(Frequency.get(fs))
        fs = self._set_fs(fs)
        self._Fs = Frequency.get(fs)
    def get_fs(self):
        return self._Fs
    def set_cf(self, cf):
        self.log.debug("set_cf(%s)", cf)
        if isinstance(cf, str):
            cf = Frequency.get(cf).raw
        cf = self._set_cf(cf)
        self._cf = Frequency.get(cf)

    def get_cf(self):
        return self._cf

    # --- Defined in child classes --- #
    def _set_fs(self, fs):
        raise NotImplementedError()
    def _set_cf(self, cf):
        raise NotImplementedError()
