"""What the DSP plots share, built on rpps: the signals in a block, the one selected for analysis brought to
baseband, and its symbols

Every plot of a source asks the same `Analyzer` (`analyzer(source)`), which works each thing out once per block:

- `survey()`: rpps' signal search over the block (`rpps.analysis.find_signals`)
- `selection(freq, bw)`: the signal the "Analysis" globals name, or the strongest one found (sticky, so a
  close runner-up does not make it jump)
- `baseband(sel)`: the selection shifted to 0 Hz, filtered and decimated (`Signal.channel`), the filter state
  carried from block to block while they are contiguous, and a short history of it
- `lock(sel, mod, baud)`: symbol rate, roll-off, timing, frequency and phase (`rpps.sync.acquire.detect`), the full
  search only every REDETECT_S seconds or when the selection changes, the quick track (timing, matched filter,
  feed-forward carrier) every block in between

rpps is imported here only when a DSP plot first runs, so pyspecan starts as fast without the plots used.
"""
import time
from dataclasses import dataclass, field

import numpy as np

from ..freq import hz
from ..settings import ANALYSIS_SETTINGS, by_key

MODULATIONS = by_key(ANALYSIS_SETTINGS, "dsp_mod").options
AUTO = MODULATIONS[1:]  # what "auto" tries
DETECT_SAMPLES = 4096   # baseband samples the full search looks at (its time grows with them)
HISTORY = 8192          # baseband samples kept for the plots
REDETECT_S = 5.0        # seconds between full searches of an unchanged selection
SPAN = 8                # matched filter half length, symbols
MIN_SAMPLES = 512       # baseband samples needed to look for symbols
TIMING_SAMPLES = 2048   # latest baseband samples the symbol timing is searched on
LOCK_LINE = 5.0         # symbol rate line strength over its floor needed to lock (noise reaches 3-4, as rpps' Acquire)

class NoLock(Exception):
    """The selection holds no symbols to lock to (a carrier, noise), the message says why"""

@dataclass
class Selection:
    """The signal being analysed: absolute center and width [Hz], and whether the search picked it"""
    freq: float
    width: float
    auto: bool
    signal: object = field(repr=False, default=None) # rpps Signal, for its channel

    @property
    def key(self) -> tuple:
        return (round(self.freq, 1), round(self.width, 1))

@dataclass
class Lock:
    """The selection's symbols. x: the baseband samples they came from (at Fs), centres: each symbol's instant in x,
    syms: frequency / phase / gain corrected (unit rms), points: the constellation (unit rms)"""
    mod: str
    baud: float
    sps: float
    beta: float
    cfo: float      # Hz
    phase: float    # rad, at the first symbol
    gain: float
    x: np.ndarray
    Fs: float
    centres: np.ndarray
    syms: np.ndarray
    points: np.ndarray
    esn0: float
    evm: float
    detected: float # time.monotonic() of the full search the parameters came from

    def derotated(self) -> np.ndarray:
        """x with the carrier offset and phase taken out, scaled so the symbols are unit rms"""
        n = np.arange(len(self.x))
        return self.x * np.exp(-2j*np.pi*self.cfo*(n - self.centres[0])/self.Fs - 1j*self.phase) / self.gain

    def decisions(self) -> np.ndarray:
        """The nearest constellation point to each symbol"""
        return self.points[np.argmin(np.abs(self.syms[:, None] - self.points[None, :]), axis=1)]

def analyzer(source) -> "Analyzer":
    """The analyzer every plot of `source` shares"""
    an = getattr(source, "_dsp_analyzer", None)
    if an is None:
        an = source._dsp_analyzer = Analyzer(source)
    return an

def rrc(t: np.ndarray, beta: float) -> np.ndarray:
    from rpps.signal.filters.shaping import rrc_pulse
    return rrc_pulse(t, beta)

def fast_tau(x: np.ndarray, sps: float, beta: float, lo: int = 0, hi: int | None = None, grid: int = 16) -> float:
    """rpps' best_tau (the symbol timing in [0, sps) that maximises the matched filter's output energy, on the
    absolute lattice tau + k sps) for a part x[lo:hi], at a fraction of the cost: the matched filter runs once as a
    convolution, its output is interpolated `grid` times finer by FFT, and each candidate timing reads its energy off
    that, where best_tau builds the filter matrix again for every candidate"""
    from rpps.math.interp import peak
    hi = len(x) if hi is None else hi
    seg = np.asarray(x[lo:hi], dtype=np.complex128)
    L = int(np.ceil(SPAN * sps))
    if len(seg) < 4 * L:
        from rpps.sync.time.mat import best_tau
        return best_tau(x, sps, beta, SPAN, lo, hi, grid)[0]
    h = rrc(np.arange(-L, L + 1) / sps, beta)
    z = np.convolve(seg, h / np.sqrt(np.sum(h**2)), "same")[L:-L] # z[i] is the output at sample lo + L + i
    n = len(z)
    Z = np.fft.fft(z)
    pad = np.zeros(n * grid, complex)
    half = n // 2
    pad[:half], pad[-(n - half):] = Z[:half], Z[half:]
    zu = np.abs(np.fft.ifft(pad) * grid) ** 2 # at (lo + L + i / grid)
    start = lo + L + 2 * sps # clear of the interpolation's wrap at the ends
    stop = lo + L + n - 2 * sps
    energy = np.zeros(grid)
    for g in range(grid):
        tau = g * sps / grid
        k = np.arange(np.ceil((start - tau) / sps), np.floor((stop - tau) / sps) + 1)
        idx = np.rint((tau + k * sps - lo - L) * grid).astype(np.int64)
        idx = idx[(idx >= 0) & (idx < len(zu))]
        energy[g] = zu[idx].mean() if len(idx) else 0.0
    g, d = peak(energy, circular=True, log=False)
    return float(((g + d) * sps / grid) % sps)

def track_timing(x: np.ndarray, sps: float, beta: float) -> tuple[float, float]:
    """(sps, tau) over x: a rate a little off makes the timing drift across x, the drift between its first and last
    TIMING_SAMPLES corrects the rate (as rpps' detector refines it, one round: the lock keeps the result, so it
    converges block by block). tau is from the latest samples, the symbol lattice being absolute"""
    n = len(x)
    seg = min(TIMING_SAMPLES, n // 2)
    end = n - seg
    if end > 4 * seg // 3: # far enough apart to see a drift
        a = fast_tau(x, sps, beta, 0, seg)
        z = fast_tau(x, sps, beta, end, n)
        drift = (z - a + sps/2) % sps - sps/2
        sps += drift / (end / sps)
    return sps, fast_tau(x, sps, beta, end)

def _strength(s) -> float:
    """How strong a found signal is: its total in-band power (a tone's SNR in its own narrow band is large, its power
    is not)"""
    if s.power is not None:
        return float(s.power)
    return (s.snr if s.snr is not None else s.height) + 10*np.log10(max(s.width, 1.0))

class Analyzer:
    def __init__(self, source):
        self.source = source
        self._tick = None
        self._surveys: dict = {}
        self._auto: Selection | None = None
        self._bb_key = None     # channel the baseband history is of
        self._bb_front = None
        self._bb_stream = None
        self._bb_seq = None
        self._bb = np.zeros(0, np.complex64)
        self._bb_Fs = 0.0
        self._locks: dict = {}
        self._nolock: dict = {} # lock key -> (time, why): not searched again for REDETECT_S
        self._points: dict = {}

    def _new_tick(self):
        tick = (self.source.seq, self.source.epoch)
        if tick != self._tick:
            self._tick = tick
            self._surveys = {}
            self._locks = {k: v for k, v in self._locks.items() if k[0] == "last"} # keep what tracking starts from
        return tick

    # --- signals --- #
    def survey(self, min_snr: float | None = None):
        """rpps Survey of the block (a list of Signal by frequency), None without samples"""
        self._new_tick()
        if min_snr not in self._surveys:
            samps = np.asarray(self.source.samples)
            if len(samps) < 256:
                return None
            from rpps.analysis import find_signals
            sv = find_signals(samps, self.source.fs, cf=self.source.cf, min_snr_db=min_snr)
            sv[:] = [s for s in sv if not s.holds] # a band holding others is a raised floor
            self._surveys[min_snr] = sv
        return self._surveys[min_snr]

    def selection(self, freq_text: str = "", bw_text: str = "") -> Selection | None:
        """The signal to analyse: the one at `freq_text` (the found one nearest it, or `bw_text` wide when given),
        else the strongest found. None when there is nothing"""
        from rpps.analysis import Signal
        fs, cf = self.source.fs, self.source.cf
        f = hz(freq_text, cf) if str(freq_text).strip() else None
        bw = hz(bw_text, 0.0) if str(bw_text).strip() else 0.0
        if f is not None and bw > 0:
            return Selection(f, bw, False, Signal(f - cf, bw, 0.0, 0.0, Fs=fs, cf=cf))
        sv = self.survey()
        if not sv:
            return None
        if f is not None:
            s = min(sv, key=lambda s: abs(s.freq - f))
            return Selection(s.freq, s.width, False, s)
        best = max(sv, key=_strength)
        old = self._auto
        if old is not None and abs(best.freq - old.freq) < old.width/2 and 0.75 < best.width/old.width < 1.33:
            return old # the same signal: keep the channel (and what was locked on it)
        self._auto = Selection(best.freq, best.width, True, best)
        return self._auto

    # --- baseband --- #
    def baseband(self, sel: Selection) -> tuple[np.ndarray, float]:
        """(the selection at baseband, its rate): the latest HISTORY samples, this block's last"""
        from rpps.base import Data
        src = self.source
        key = (src.epoch, src.fs, sel.key)
        if key == self._bb_key and src.seq == self._bb_seq:
            return self._bb, self._bb_Fs
        go_on = key == self._bb_key and self._bb_seq is not None and src.seq == self._bb_seq + 1
        if not go_on:
            ch = sel.signal.channel()
            self._bb_front, self._bb_Fs, self._bb_stream = ch.front, ch.Fs, None
            self._bb = np.zeros(0, np.complex64)
        samps = np.asarray(src.samples, dtype=np.complex64)
        kw = {"stream": self._bb_stream} if go_on and self._bb_stream is not None else {}
        out = Data(samps, Fs=src.fs, **kw) + self._bb_front
        self._bb_stream = out.stream
        x = np.asarray(out.data, dtype=np.complex64)
        if not go_on:
            x = x[min(len(x)//8, 256):] # the filters starting up
        self._bb = np.concatenate((self._bb, x))[-HISTORY:]
        self._bb_key, self._bb_seq = key, src.seq
        return self._bb, self._bb_Fs

    # --- symbols --- #
    def points(self, mod: str) -> np.ndarray:
        if mod not in self._points:
            from rpps.sync.acquire import candidates
            self._points[mod] = candidates([mod])[mod]
        return self._points[mod]

    def lock(self, sel: Selection, mod: str = "auto", baud_text: str = "") -> Lock | None:
        """The selection's symbols, None while there are too few samples to find them. Raises NoLock when the
        search finds no symbol rate (without a rate given)"""
        from rpps.sync.acquire import correct, detect, symmetry
        from rpps.sync.quality import measure
        from rpps.sync.time.mat import centres_in, matrix_mf
        self._new_tick()
        x, Fs = self.baseband(sel)
        if len(x) < MIN_SAMPLES:
            return None
        baud = hz(baud_text, 0.0) if str(baud_text).strip() else None
        key = (sel.key, mod, baud, Fs)
        if key in self._locks:
            return self._locks[key]
        prev = self._locks.get(("last", key))
        now = time.monotonic()
        failed = self._nolock.get(key)
        if failed is not None and now - failed[0] <= REDETECT_S:
            raise NoLock(failed[1])
        if prev is None or now - prev.detected > REDETECT_S:
            det = detect(x[-DETECT_SAMPLES:], Fs, list(AUTO) if mod == "auto" else [mod], baud=baud)
            if baud is None and det.line is not None and det.line < LOCK_LINE:
                why = f"no symbol rate (line {det.line:.1f}): a carrier or noise?"
                self._nolock[key] = (now, why)
                raise NoLock(why)
            self._nolock.pop(key, None)
            found, b, beta, detected = det.mod, det.baud, det.beta, now
        else:
            found, b, beta, detected = prev.mod, prev.baud, prev.beta, prev.detected
        sps, tau = track_timing(x, Fs / b, beta)
        b = Fs / sps
        c = centres_in(len(x), tau + np.ceil((SPAN*sps + 5 - tau)/sps)*sps, sps, SPAN)
        if len(c) < 16:
            return None
        y = matrix_mf(x, c, sps, beta, SPAN)
        gain = float(np.sqrt(np.mean(np.abs(y)**2))) or 1.0
        pts = self.points(found)
        syms, cfo, phase = correct(y / gain, pts, symmetry(pts))
        q = measure(syms, pts)
        lk = Lock(found, b, sps, beta, cfo*b, phase, gain, x, Fs, c, syms, pts, q.esn0_db, q.evm_pct, detected)
        self._locks[key] = self._locks[("last", key)] = lk
        return lk
