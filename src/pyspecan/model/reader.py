"""File reader"""
import pathlib
from enum import Enum

import numpy as np
from numpy._typing._array_like import NDArray

from .. import err

def read_ci8(path, count, offset):
    samples = np.fromfile(path, offset=offset, count=count, dtype=np.int8)
    return samples.astype(np.float32).view(dtype=np.complex64)
def read_ci16(path, count, offset):
    samples = np.fromfile(path, offset=offset, count=count, dtype=np.int16)
    return samples.astype(np.float32).view(dtype=np.complex64)
def read_cf16(path, count, offset):
    samples = np.fromfile(path, offset=offset, count=count, dtype=np.float16)
    return samples.astype(np.float32).view(dtype=np.complex64)
def read_cf32(path, count, offset):
    samples = np.fromfile(path, offset=offset, count=count, dtype=np.float32)
    return samples.view(dtype=np.complex64)
def read_cf64(path, count, offset):
    samples = np.fromfile(path, offset=offset, count=count, dtype=np.float64)
    return samples.astype(np.float32).view(dtype=np.complex64)

class Format(Enum):
    ci8  = (2, read_ci8)
    ci16 = (4, read_ci16)
    cf16 = (4, read_cf16)
    cf32 = (8, read_cf32)
    cf64 = (16, read_cf64)

    def size(self):
        return self.value[0]

    def read(self, path, count: int, offset: int):
        return self.value[1](path, count, offset*self.size())

    @classmethod
    def choices(cls):
        return [inst.name for inst in cls]

class Reader:
    __slots__ = (
        "_path", "_fmt",
        "_fsize", "cur_samp", "max_samp"
    )
    def __init__(self, fmt, path):
        self._path: pathlib.Path = None # type: ignore
        self._fmt: Format = None # type: ignore
        self._fsize = 0
        self.cur_samp = 0
        self.max_samp = -1

        self.set_path(path)
        self.set_fmt(fmt)

    def show(self, ind=0):
        print(" "*ind + f"{self.percent():06.2f}% [{self.fmt.name}] {self.path}")
        print(" "*ind + f"{self.cur_samp}/{self.max_samp}")

    def get_path(self):
        return self._path
    def set_path(self, path):
        if path is None or path == "":
            return
        path = pathlib.Path(path)

        if not path.exists():
            return
        if not path == self._path:
            self._fsize = path.stat().st_size
            if not self._fmt is None:
                self.max_samp = self._fsize // self.fmt.size()
        self._path = path
        self.reset()
    path = property(get_path, set_path)

    def get_fmt(self):
        return self._fmt
    def set_fmt(self, fmt):
        self._fmt = Format[fmt]
        if not self._fsize == 0 and not self._fmt is None:
            self.max_samp = self._fsize // self.fmt.size()
    fmt = property(get_fmt, set_fmt)

    def reset(self):
        self.cur_samp = 0

    def next(self, count: int):
        count *= 2
        if self.cur_samp + count > self.max_samp:
            raise err.Overflow(f"{self.cur_samp}+{count} > {self.max_samp}")
        samps = self._read(count)
        self.cur_samp += count
        return samps

    def prev(self, count: int):
        count *= 2
        if self.cur_samp - count < 0:
            raise err.Overflow(f"{self.cur_samp}-{count} < 0")
        self.cur_samp -= count
        samps = self._read(count)
        return samps

    def _read(self, count: int):
        """Read <count> samples"""
        if self.path is None:
            return
        samps = self.fmt.read(self.path, count, self.cur_samp)
        return samps

    def forward(self, count: int):
        """Return <count> samples until EOF"""
        while self.cur_samp + count <= self.max_samp:
            # return self.next(count)
            yield self.next(count)

    def reverse(self, count: int):
        while self.cur_samp - count >= 0:
            # return self.prev(count)
            yield self.prev(count)

    def percent(self):
        """Return percent of file read"""
        return float(self.cur_samp/self.max_samp)*100

    def __call__(self, count):
        return self.forward(count)
