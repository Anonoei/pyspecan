"""What the DSP plots share, built on rpps: the signals in a block, the one selected for analysis brought to
baseband, and its symbols

Every plot of a source asks the same `Analyzer` (`analyzer(source)`), which works each thing out once per block:

- `survey()`: rpps' signal search over the block (`rpps.analysis.find_signals`), each signal keeping its id from block
  to block (`Survey.match`)
- `selection(freq, bw)`: the signal the "Analysis" globals name (`rpps.analysis.measure_band`), or the strongest one
  found (sticky: it stays the selection while it is there, so a close runner-up does not make it jump)
- `baseband(sel)`: the selection shifted to 0 Hz, filtered and decimated (`Signal.channel`), the filter state
  carried from block to block while they are contiguous, and a short history of it
- `lock(sel, mod, baud)`: its symbols (`rpps.sync.Lock`): a full search once, then followed block by block, searched
  again when rpps calls the lock stale (the signal changed rate, modulation or went away)

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
SPAN = 8                # matched filter half length, symbols
MIN_SAMPLES = 512       # baseband samples needed to look for symbols
RECHECK_S = 1.0         # seconds between checks that the modulation is still the one found (about half a follow's cost)

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
    syms: frequency / phase / gain corrected (unit rms), points: the constellation (unit rms). rpps: its rpps.sync.Lock"""
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
    rpps: object = field(repr=False, default=None)

    @classmethod
    def of(cls, lk, x: np.ndarray, Fs: float) -> "Lock":
        """From an rpps.sync.Lock of x"""
        d = lk.det
        return cls(d.mod, float(d.baud), float(d.sps), float(d.beta), float(d.cfo), float(d.phase), float(d.gain), x, Fs,
                   lk.centres, lk.symbols, lk.points, float(lk.quality.esn0_db), float(lk.quality.evm_pct), lk)

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
    from rpps.signal.filters import rrc_pulse
    return rrc_pulse(t, beta)

class Analyzer:
    def __init__(self, source):
        self.source = source
        self._tick = None
        self._surveys: dict = {}
        self._last_survey = None # the previous block's, its ids carried over
        self._auto: Selection | None = None
        self._bb_key = None     # channel the baseband history is of
        self._bb_front = None
        self._bb_stream = None
        self._bb_seq = None
        self._bb = np.zeros(0, np.complex64)
        self._bb_Fs = 0.0
        self._locks: dict = {}  # this block's Lock per lock key
        self._found: dict = {}  # lock key -> the rpps.sync.Lock followed from block to block
        self._checked: dict = {} # lock key -> time.monotonic() of the last modulation recheck

    def _new_tick(self):
        tick = (self.source.seq, self.source.epoch)
        if tick != self._tick:
            self._tick = tick
            self._surveys = {}
            self._locks = {}
        return tick

    # --- signals --- #
    def survey(self, min_snr: float | None = None):
        """rpps Survey of the block (a list of Signal by frequency, each with an id kept from block to block), None
        without samples"""
        self._new_tick()
        if min_snr not in self._surveys:
            samps = np.asarray(self.source.samples)
            if len(samps) < 256:
                return None
            from rpps.analysis import find_signals
            sv = find_signals(samps, self.source.fs, cf=self.source.cf, min_snr_db=min_snr, nested=False)
            if min_snr is None:
                if self._last_survey is not None:
                    sv.match(self._last_survey)
                self._last_survey = sv
            self._surveys[min_snr] = sv
        return self._surveys[min_snr]

    def selection(self, freq_text: str = "", bw_text: str = "") -> Selection | None:
        """The signal to analyse: the one at `freq_text` (the found one nearest it, or `bw_text` wide when given),
        else the strongest found. None when there is nothing"""
        fs, cf = self.source.fs, self.source.cf
        f = hz(freq_text, cf) if str(freq_text).strip() else None
        bw = hz(bw_text, 0.0) if str(bw_text).strip() else 0.0
        if f is not None and bw > 0:
            from rpps.analysis import Signal, measure_band
            samps = np.asarray(self.source.samples)
            # measured like a found one, so typed and found signals read alike (too few samples: the band as given)
            sig = measure_band(samps, fs, f, bw, cf=cf) if len(samps) >= 256 else Signal(f - cf, bw, 0.0, 0.0, Fs=fs, cf=cf)
            return Selection(f, bw, False, sig)
        sv = self.survey()
        if not sv:
            return None
        if f is not None:
            s = min(sv, key=lambda s: abs(s.freq - f))
            return Selection(s.freq, s.width, False, s)
        old = self._auto
        same = next((s for s in sv if old is not None and s.id == old.signal.id), None)
        best = max(sv, key=lambda s: s.power) # total in-band power: a tone's SNR in its own narrow band is large, its power is not
        if same is not None and (same is best or same.power >= best.power - 3.0):
            return old # still there and among the strongest: keep the channel (and what was locked on it)
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
            x = x[ch.settle:] # the filters starting up
        self._bb = np.concatenate((self._bb, x))[-HISTORY:]
        self._bb_key, self._bb_seq = key, src.seq
        return self._bb, self._bb_Fs

    # --- symbols --- #
    def lock(self, sel: Selection, mod: str = "auto", baud_text: str = "") -> Lock | None:
        """The selection's symbols, None while there are too few samples to find them. Raises NoLock when the
        search finds none (without a rate given), with why"""
        from rpps.errors import NoLock as RppsNoLock
        from rpps.sync import Lock as RppsLock
        self._new_tick()
        x, Fs = self.baseband(sel)
        if len(x) < MIN_SAMPLES:
            return None
        baud = hz(baud_text, 0.0) if str(baud_text).strip() else None
        key = (sel.key, mod, baud, Fs)
        if key in self._locks:
            return self._locks[key]
        prev = self._found.get(key)
        try:
            if prev is not None and not prev.stale:
                now = time.monotonic()
                recheck = now - self._checked.get(key, 0.0) >= RECHECK_S
                if recheck:
                    self._checked[key] = now
                try:
                    lk = prev.update(x, recheck=recheck)
                except RppsNoLock:
                    lk = None
                if lk is None or lk.stale: # it changed: search again
                    prev = None
            if prev is None or prev.stale:
                names = list(AUTO) if mod == "auto" else [mod]
                lk = RppsLock.find(x[-DETECT_SAMPLES:], Fs, names=names, span=SPAN, baud=baud).update(x, recheck=False)
                self._checked[key] = time.monotonic()
        except RppsNoLock as e:
            self._found.pop(key, None)
            raise NoLock(str(e)) from None
        self._found[key] = lk
        out = self._locks[key] = Lock.of(lk, x, Fs)
        return out
