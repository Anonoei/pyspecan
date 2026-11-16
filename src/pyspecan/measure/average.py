"""Trace averaging"""
from collections import deque

import numpy as np

from .units import db_to_lin, lin_to_db

MODES = ("off", "power", "log", "exp")

class Averager:
    """off: passthrough, power: mean of the last `count` traces in linear power,
    log: mean of the last `count` traces in dB, exp: exponential average (alpha = 1/count) in linear power"""
    def __init__(self, mode: str = "off", count: int = 10):
        if mode not in MODES:
            raise ValueError(f"unknown average mode {mode!r}")
        self.mode = mode
        self.count = max(1, int(count))
        self.reset()

    def reset(self):
        self._buf: deque = deque()
        self._sum = None
        self._state = None
        self.n = 0

    def update(self, rows_db: np.ndarray) -> np.ndarray:
        """Feed (k, n) dB rows, returns the averaged (n,) trace after the last row"""
        rows_db = np.atleast_2d(np.asarray(rows_db, dtype=float))
        if self.mode == "off" or self.count == 1:
            self.n = 1
            return rows_db[-1]
        if self._shape_changed(rows_db.shape[-1]):
            self.reset()
        for row in rows_db:
            self._push(row)
        return self._result()

    def _shape_changed(self, n: int) -> bool:
        have = self._state if self._state is not None else (self._sum if self._sum is not None else None)
        return have is not None and have.shape[-1] != n

    def _push(self, row_db):
        if self.mode == "exp":
            lin = db_to_lin(row_db)
            if self._state is None:
                self._state = lin.copy()
            else:
                self._state += (lin - self._state) / self.count
            self.n = min(self.n + 1, self.count)
            return
        item = db_to_lin(row_db) if self.mode == "power" else row_db.copy()
        self._buf.append(item)
        self._sum = item.copy() if self._sum is None else self._sum + item
        if len(self._buf) > self.count:
            self._sum -= self._buf.popleft()
        self.n = len(self._buf)

    def _result(self) -> np.ndarray:
        if self.mode == "exp":
            return lin_to_db(self._state)
        mean = self._sum / len(self._buf)
        return lin_to_db(mean) if self.mode == "power" else mean
