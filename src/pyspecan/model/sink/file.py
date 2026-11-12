"""File reader"""
import pathlib

import numpy as np
from numpy._typing._array_like import NDArray
import pysdrlib
from pysdrlib import Formats as _Formats
from pysdrlib import File as _File

# reading from a file that was never opened: newer pysdrlib raises NotOpen, older ones fail on a missing handle
NotOpen = getattr(getattr(pysdrlib, "err", None), "NotOpen", AttributeError)

from ...utils import args
from .sink import Sink, args_sink

from ... import err

# IQ formats only: real formats would yield real samples
FORMATS = [f.name for f in _Formats if f.is_complex]
DEFAULT_FORMAT = "cf64"

def args_file(parser):
    sink = args.get_group(parser, "Sink (FILE)")
    args_sink(sink)
    sink.add_argument("-f", "--path", default=None, help="file path")
    sink.add_argument("-d", "--fmt", choices=FORMATS, default=DEFAULT_FORMAT, help="data format")

class SinkFile(Sink):
    SEEKABLE = True
    __slots__ = (
        "dev",
    )
    def __init__(self, model, **kwargs):
        path = kwargs.get("path", None)
        fmt = kwargs.get("fmt", DEFAULT_FORMAT)
        super().__init__(model, **kwargs)
        self.dev = _File()

        self.set_fmt(fmt)
        self.set_path(path) # opens it

    def show(self, ind=0):
        print(" "*ind + f"{self.percent():06.2f}% [{self.dev.fmt.name}] {self.dev.path}")
        print(" "*ind + f"{self.dev.cur_samp}/{self.dev.max_samp}")

    def ready(self):
        return self.get_path() is not None

    def get_path(self):
        return self.dev.get_path()
    def set_path(self, path):
        if path is None or path == "":
            return
        path = pathlib.Path(path)

        if not path.exists():
            return
        if getattr(self.dev, "f", None) is not None: # switching files
            self.dev.close()
        self.dev.set_path(path)
        self.dev.open()
        self.reset()

    def get_fmt(self):
        return self.dev.get_fmt()
    def set_fmt(self, fmt):
        if fmt not in FORMATS:
            raise ValueError(f"unknown format {fmt!r}")
        self.dev.set_fmt(fmt)

    def _set_fs(self, fs):
        return fs
    def _set_cf(self, cf):
        return cf

    def reset(self):
        self.dev.reset()

    def next(self, count: int):
        # self.log.trace("next(%s)", count)
        try:
            samples = self.dev.next(count)
        except pysdrlib.file.err.Overflow:
            return False
        except (AttributeError, NotOpen):
            self.dev.open()
            samples = self.dev.next(count)
        self._samples = samples
        # self._psd = None
        return True

    def prev(self, count: int):
        try:
            samples = self.dev.prev(count)
        except pysdrlib.file.err.Overflow:
            return False
        except (AttributeError, NotOpen):
            self.dev.open()
            samples = self.dev.prev(count)
        self._samples = samples
        # self._psd = None
        return True

    def seek(self, samp: int):
        """Jump to sample `samp`"""
        self.dev.cur_samp = max(0, min(int(samp), self.max_samp))

    def forward(self, count: int):
        return self.dev.forward(count)

    def reverse(self, count: int):
        return self.dev.reverse(count)

    def percent(self):
        return self.dev.percent()

    def cur_time(self):
        return self.dev.cur_samp/self.get_fs()
    def tot_time(self):
        return self.dev.max_samp/self.get_fs()
    def skip_time(self, s):
        samps = int(self.model.Fs * s)
        # print(f"Skipping {s:.3f}s, {samps} ({samps/self.reader.max_samp*100:.2f}%)")
        self.dev.cur_samp += samps

    @property
    def cur_samp(self):
        return self.dev.cur_samp

    @property
    def max_samp(self):
        return self.dev.max_samp
