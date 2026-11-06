"""Source: the spectra every plot in a view shares

The model hands the controller one block of samples per tick. Plots slice that
block with a `Stream`, so swept and realtime plots can run side by side and both
see every sample:

    swept     back to back nfft sized frames          (hop = nfft)
    rt        overlapping frames, see Model overlap   (hop = nfft * (1 - overlap))

A stream keeps the samples that did not fill a frame and prepends them to the
next block, so frames stay continuous across ticks. Streams are shared, plots
asking for the same (mode, nfft, window) get the same frames, computed once per tick.
"""
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from ..utils.window import WindowLUT


class Stream:
    """Cuts blocks into frames and transforms them, carrying leftover samples between blocks"""
    def __init__(self, nfft: int, hop: int, window: str):
        self.nfft = nfft
        self.hop = hop
        self.win = WindowLUT[window](nfft)
        self.carry = np.empty(0, dtype=np.complex64)
        self.seen = -2        # tick of the last block consumed
        self.result = np.empty((0, nfft), dtype=np.complex64)

    def frames(self, samples: np.ndarray, seq: int) -> np.ndarray:
        """(k, nfft) centered spectra of the frames completed by block `seq`, k may be 0"""
        if seq == self.seen:
            return self.result
        if seq != self.seen + 1: # missed a block, the carried samples are no longer adjacent
            self.carry = self.carry[:0]
        self.seen = seq
        buf = np.concatenate((self.carry, samples)) if self.carry.size else np.asarray(samples)
        n = len(buf)
        if n < self.nfft:
            self.carry = buf.copy()
            self.result = np.empty((0, self.nfft), dtype=np.complex64)
            return self.result
        k = (n - self.nfft) // self.hop + 1
        view = sliding_window_view(buf, self.nfft)[::self.hop][:k]
        self.result = np.fft.fftshift(np.fft.fft(view * self.win, axis=1), axes=1)
        self.carry = buf[k*self.hop:].copy()
        return self.result

class Source:
    """What plots read from: the model's current block and shared spectra streams"""
    def __init__(self, model):
        self.model = model
        self.seq = 0
        self._streams: dict[tuple, Stream] = {}

    # --- per tick --- #
    def tick(self):
        """A new block is in the model"""
        self.seq += 1
        self._streams = {k: s for k, s in self._streams.items() if s.seen >= self.seq - 2}

    def reset(self):
        """Forget carried samples, call after the sample position jumps"""
        self._streams.clear()

    # --- model view --- #
    @property
    def samples(self) -> np.ndarray:
        return self.model.samples

    @property
    def fs(self) -> float:
        return self.model.get_fs().raw

    @property
    def cf(self) -> float:
        return self.model.get_cf().raw

    @property
    def nfft(self) -> int:
        return self.model.get_nfft()

    @property
    def overlap(self) -> float:
        return self.model.get_overlap()

    def freq_range(self) -> tuple[float, float]:
        fs, cf = self.fs, self.cf
        return cf - fs/2, cf + fs/2

    def hop(self, mode: str, nfft: int) -> int:
        if mode == "swept":
            return nfft
        if mode == "rt":
            return max(1, int(nfft * (1 - self.overlap)))
        raise ValueError(f"unknown mode {mode!r}")

    def spectra(self, mode="swept", window="blackman", nfft: int | None = None) -> np.ndarray:
        """(k, nfft) complex spectra, centered on cf, of the frames completed by this tick's block"""
        nfft = nfft or self.nfft
        hop = self.hop(mode, nfft)
        key = (nfft, hop, window)
        stream = self._streams.get(key)
        if stream is None:
            stream = self._streams[key] = Stream(nfft, hop, window)
        return stream.frames(self.samples, self.seq)
