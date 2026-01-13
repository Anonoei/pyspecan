"""File reader"""
import pathlib
from enum import Enum

import numpy as np
from numpy._typing._array_like import NDArray
import pysdrlib
from pysdrlib import Formats as _Formats
from pysdrlib import File as _File

from ...utils import args
from .sink import Sink, args_sink

from ... import err

class Format(Enum):
    ci8  = _Formats.ci8
    ci16 = _Formats.ci16
    cf32 = _Formats.cf32
    cf64 = _Formats.cf64
    cf128 = _Formats.cf128

    @classmethod
    def choices(cls):
        return [inst.name for inst in cls]

def args_file(parser):
    sink = args.get_group(parser, "Sink (FILE)")
    args_sink(sink)
    sink.add_argument("-f", "--path", default=None, help="file path")
    sink.add_argument("-d", "--fmt", choices=Format.choices(), default=Format.cf32.name, help="data format")

class SinkFile(Sink):
    __slots__ = (
        "dev", "fmt"
    )
    def __init__(self, model, **kwargs):
        path = kwargs.get("path", None)
        fmt = kwargs.get("fmt", Format.cf32.name)
        super().__init__(model, **kwargs)
        self.dev = _File()

        self.set_fmt(fmt)
        self.set_path(path)
        self.dev.open()

    def show(self, ind=0):
        print(" "*ind + f"{self.percent():06.2f}% [{self.dev.fmt.name}] {self.dev.path}")
        print(" "*ind + f"{self.dev.cur_samp}/{self.dev.max_samp}")

    def get_path(self):
        return self.dev.get_path()
    def set_path(self, path):
        if path is None or path == "":
            return
        path = pathlib.Path(path)

        if not path.exists():
            return
        self.dev.set_path(path)
        self.reset()

    def get_fmt(self):
        return self.fmt # TODO: is this needed?
    def set_fmt(self, fmt):
        self.fmt = Format[fmt]
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
        self._samples = samples
        # self._psd = None
        return True

    def prev(self, count: int):
        try:
            samples = self.dev.prev(count)
        except pysdrlib.file.err.Overflow:
            return False
        self._samples = samples
        # self._psd = None
        return True

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
