"""How a signal is cut in time: Hopping (the dwells of a frequency hopper), Bursts (TDMA bursts demodulated one by one)
and Frame Raster (the period the symbols repeat with, and its unique word). Each runs rpps' analysis in the background
(`common.Job`) and draws the latest result"""
import numpy as np

from ...measure import trigger
from ..base import About, plot
from ..frame import BLUE, GREEN, IMAGE, LINE, RED, SCATTER, YELLOW, Axis, Band, Frame, Image, Marker, Table, TableRow, Trace, fmt_time
from ..freq import SETTING_CMAP, fmt_hz, hz
from ..reduce import envelope
from ..settings import Setting
from .analyzer import analyzer
from .common import DSPPlot, Job

CONFIRM = 2 # frame searches in a row that must find a period before it is drawn
DROP = 3    # searches in a row that do not find the period drawn before it is dropped
SLOT_COLORS = (GREEN, BLUE, YELLOW, "#c678dd", "#56b6c2", "#e5a04b")
MAX_ROWS = 512 # image rows drawn at most (rows beyond are max-pooled)


def _image(db: np.ndarray, span: float = 50.0) -> np.ndarray:
    """dB rows as a uint8 image over the top `span` dB, the newest (last) row on top"""
    top = float(np.max(db)) if db.size else 0.0
    im = np.clip((db - (top - span)) * (255.0 / span), 0, 255).astype(np.uint8)
    if len(im) > MAX_ROWS:
        k = int(np.ceil(len(im) / MAX_ROWS))
        im = im[:len(im) // k * k].reshape(-1, k, im.shape[1]).max(axis=1)
    return im[::-1]


# --- hopping --- #
def track_hops(x: np.ndarray, fs: float, nfft: int, snr_db: float):
    """(rpps Hops, the short-time spectrum in dB) of the block. Runs on a Job's thread"""
    from rpps.analysis.spectrum import hopping
    h = hopping.track(x, fs, nfft=nfft, snr_db=snr_db)
    hop = nfft // 2
    k = (len(x) - nfft) // hop + 1
    S = np.abs(np.fft.fftshift(np.fft.fft(x[np.arange(nfft)[None, :] + hop * np.arange(max(k, 0))[:, None]] * np.hanning(nfft), axis=1), axes=1)) ** 2
    return h, 10 * np.log10(np.maximum(S, 1e-30))


@plot("Hopping")
class Hopping(DSPPlot):
    """A frequency hopper's dwells over the whole span: a short-time spectrum (frames much shorter than a dwell) with
    each dwell rpps finds boxed, and below it how often each channel of the hop set was visited since the last
    reset. The readout has the hop set (channels, their spacing), the dwell time and the hop rate"""
    TITLE = "Hopping"
    CATEGORY = "Channel and signal analysis"
    FEATURES = frozenset({LINE, IMAGE})
    ABOUT = About(
        data="The whole block, a short-time spectrum (FFT frames overlapping by half); each frame's strongest peak over "
             "its floor, runs of frames on one channel made dwells (rpps.analysis.spectrum.hopping), in the background",
        shows="Frequency against time with every dwell boxed; the visits to each channel since the last reset; the hop "
              "set, its spacing, the dwell time and hop rate",
        use=("Measure a hopper's dwell time, hop rate and channel spacing",
             "Find the hop set (and the channels a hopper avoids)",
             "Tell hopping from a wideband signal"),
        cost=8, # the tracking included (on its own thread)
    )
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("nfft", "FFT size", "select", default="256", options=("64", "128", "256", "512", "1024", "2048"), reset=True,
                group="Hopping", help="frame length: shorter than a dwell, with bins narrower than the channel spacing"),
        Setting("snr_db", "SNR (dB)", "number", default=6.0, min=0.0, max=40.0, step=1, reset=True, group="Hopping",
                help="how far a frame's peak must rise over its median bin to count"),
        SETTING_CMAP,
    )

    def reset(self):
        super().reset()
        self.job = Job("hopping")
        self.visits: dict[float, int] = {} # channel (absolute Hz) -> dwells seen there
        self._counted = None                # the result the visits include

    def render(self):
        x = np.asarray(self.source.samples)
        n = int(self.nfft) # type: ignore
        if not len(x):
            return None
        fs, cf = self.source.fs, self.source.cf
        if len(x) < 4 * n:
            return Frame([Axis(xmin=cf - fs / 2, xmax=cf + fs / 2, xfmt="freq", ylabel="Time (ms)")], title=self.TITLE,
                         readout=[("Hopping", f"the block ({len(x)} samples) is shorter than 4 FFTs: a smaller FFT size")])
        self.job.submit(track_hops, np.array(x), fs, n, self.snr_db) # type: ignore
        lo, hi = cf - fs / 2, cf + fs / 2
        res = self.job.result
        readout = []
        if res is None:
            axes = [Axis(xmin=lo, xmax=hi, xfmt="freq", ymin=0.0, ymax=len(x) / fs * 1e3, ylabel="Time (ms)")]
            return Frame(axes, title=self.TITLE, readout=self.job.readout())
        h, db = res
        if res is not self._counted:
            self._counted = res
            tol = 2 * fs / n
            for d in h.dwells:
                f = cf + d.freq
                near = min(self.visits, key=lambda c: abs(c - f), default=None)
                key = near if near is not None and abs(near - f) <= tol else f
                self.visits[key] = self.visits.get(key, 0) + 1
        T = (len(db) * (n // 2) + n // 2) / fs * 1e3
        w = (h.spacing * 0.8) if h.spacing else 2 * fs / n
        boxes = [Band(cf + d.freq - w / 2, cf + d.freq + w / 2, GREEN, 0.18, ylo=d.start * 1e3, yhi=d.end * 1e3)
                 for d in h.dwells[:400]]
        axes = [Axis(xmin=lo, xmax=hi, xfmt="freq", ymin=0.0, ymax=T, ylabel="Time (ms)",
                     image=Image(_image(db), cmap=self.cmap), bands=boxes)] # type: ignore
        if self.visits:
            top = max(self.visits.values())
            bars = [Band(f - w / 2, f + w / 2, BLUE, 0.6, ylo=0.0, yhi=float(c)) for f, c in self.visits.items()]
            axes.append(Axis(xmin=lo, xmax=hi, xfmt="freq", ymin=0.0, ymax=top * 1.15, ylabel="Dwells", bands=bars))
        readout.append(("Hopping", "yes" if h.hopping else "no"))
        readout.append(("Channels", f"{len(h.channels)} this block, {len(self.visits)} seen"))
        if h.spacing:
            readout.append(("Spacing", fmt_hz(h.spacing)))
        if h.dwell:
            readout += [("Dwell", fmt_time(h.dwell)), ("Rate", f"{h.rate:.1f} hops/s")]
        readout.append(("Active", f"{100 * h.active:.0f}%"))
        readout += self.job.readout()
        rows = [TableRow(f"C{k}", [f"C{k}", fmt_hz(f), str(c)]) for k, (f, c) in enumerate(sorted(self.visits.items()), 1)]
        return Frame(axes, title=self.TITLE, readout=readout, table=Table(["", "Channel", "Dwells"], rows))


# --- bursts --- #
def demodulate_bursts(x: np.ndarray, Fs: float, mod: str | None, baud: float | None):
    """(rpps Bursts, the power envelope (t, dB)) of the baseband block. Runs on a Job's thread"""
    from rpps.analysis.spectrum import burst
    r = burst.demodulate(x, Fs, mod=mod, baud=baud)
    p = trigger.power_db(x, max(1, int(Fs * 2e-6)))
    t, y = envelope(np.arange(len(p)) / Fs, p)
    return r, (t, y)


@plot("Bursts")
class Bursts(DSPPlot):
    """TDMA bursts of the selection, each acquired and demodulated on its own from the preamble the bursts share
    (rpps.analysis.spectrum.burst): every burst boxed on the power against time, colored by its slot (red: not
    acquired), and their data symbols as one constellation. The table lists each burst's start, symbols, carrier
    offset, EVM, frame and slot. The modulation and rate are the Analysis settings', or found"""
    TITLE = "Bursts"
    CATEGORY = "Channel and signal analysis"
    FEATURES = frozenset({LINE, SCATTER})
    ABOUT = About(
        data="The analysed signal shifted to 0 Hz and filtered, all of the block; the bursts gated, the preamble they "
             "share found, each burst acquired on it and demodulated (rpps.analysis.spectrum.burst), in the background",
        shows="Power against time with each burst boxed and colored by its slot; the bursts' data symbols; per burst "
              "its start, length, carrier offset, EVM, frame and slot; the frame period and slots",
        use=("Measure a TDMA signal's frame and slots", "Check each burst's carrier offset and EVM (one per transmitter)",
             "Find the preamble a network's bursts share"),
        cost=3, # the demodulation included (on its own thread)
    )
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("rows", "Rows", "int", default=50, min=1, max=1000, group="Display", help="bursts listed"),
    )

    def reset(self):
        super().reset()
        self.job = Job("bursts")
        self._for = None

    def render(self):
        if not len(self.source.samples):
            return None
        an = analyzer(self.source)
        sel = an.selection(self.dsp_freq, self.dsp_bw) # type: ignore
        if sel is None:
            return Frame([Axis(xfmt="time", ylabel="dB")], title=self.TITLE, readout=[("Signal", "none found")])
        if sel.key != self._for:
            self._for = sel.key
            self.job.clear()
        x, Fs = an.block(sel)
        mod = None if self.dsp_mod == "auto" else self.dsp_mod # type: ignore
        baud = hz(self.dsp_baud, 0.0) if str(self.dsp_baud).strip() else None # type: ignore
        if len(x) >= 1024:
            self.job.submit(demodulate_bursts, np.array(x), Fs, mod, baud)
        readout = self.sel_readout(sel)
        res = self.job.result
        if res is None: # the block's power meanwhile (or when rpps finds no bursts: what it looked at)
            p = trigger.power_db(x, max(1, int(Fs * 2e-6)))
            t, y = envelope(np.arange(len(p)) / Fs, p)
            readout += self.job.readout()
            return Frame([Axis(xmin=0.0, xmax=float(t[-1]) if len(t) > 1 else 1.0, xfmt="time", xlabel="Time", ylabel="dB",
                               traces=[Trace(y, t, color=YELLOW, name="power", width=1.0)] if len(t) else []),
                          Axis(xmin=-1.6, xmax=1.6, ymin=-1.6, ymax=1.6, square=True, xlabel="I", ylabel="Q")],
                         title=self.TITLE, readout=readout)
        r, (t, p) = res
        sps = Fs / r.baud
        boxes, rows, data, pre = [], [], [], []
        for k, b in enumerate(r.bursts, 1):
            n = len(b.symbols) if b.symbols is not None else 0
            a, z = b.start / Fs, (b.start + max(n, 1) * sps) / Fs
            color = RED if not b.ok else SLOT_COLORS[(b.slot or 0) % len(SLOT_COLORS)]
            label = f"{b.frame}.{b.slot}" if b.ok and b.slot is not None else f"B{k}"
            boxes.append(Band(a, z, color, 0.22, label))
            if b.ok:
                npre = len(r.preambles[b.kind]) if b.kind is not None else len(r.preamble)
                pre.append(b.symbols[:npre])
                data.append(b.symbols[npre:])
            if len(rows) < self.rows: # type: ignore
                rows.append(TableRow(f"B{k}", [f"B{k}", fmt_time(a), str(n),
                                               fmt_hz(b.cfo) if b.ok else "-", f"{100 * b.evm:.1f}%" if b.ok else "-",
                                               f"{b.frame} / {b.slot}" if b.ok and b.slot is not None else "-",
                                               str(b.kind) if b.ok else f"not acquired (score {b.score:.2f})"]))
        axes = [Axis(xmin=0.0, xmax=float(t[-1]) if len(t) else 1.0, xfmt="time", xlabel="Time", ylabel="dB",
                     traces=[Trace(p, t, color=YELLOW, name="power", width=1.0)], bands=boxes)]
        traces = []
        for name, parts, color in (("data", data, BLUE), ("preamble", pre, GREEN)):
            if parts:
                s = np.concatenate(parts)[-4000:]
                traces.append(Trace(s.imag, s.real, color=color, kind=SCATTER, name=name, alpha=0.5))
        axes.append(Axis(xmin=-1.6, xmax=1.6, ymin=-1.6, ymax=1.6, square=True, xlabel="I", ylabel="Q", traces=traces))
        ok = [b for b in r.bursts if b.ok]
        readout += [("Bursts", f"{len(r.bursts)} ({len(ok)} demodulated)"), ("Mod", r.mod),
                    ("Baud", fmt_hz(r.baud).replace("Hz", "Bd")),
                    ("Preamble", ", ".join(f"{len(q)} symbols" for q in (r.preambles or [r.preamble])))]
        if r.frame:
            readout += [("Frame", fmt_time(r.frame)), ("Slots", str(len(r.slots)))]
        if ok:
            readout.append(("EVM", f"{100 * np.median([b.evm for b in ok]):.1f}% median"))
        readout += self.job.readout()
        return Frame(axes, title=self.TITLE, readout=readout,
                     table=Table(["", "Start", "Symbols", "CFO", "EVM", "Frame / slot", "Kind"], rows))



# --- frames --- #
def find_frames(y: np.ndarray, mod: str, points: np.ndarray):
    """Of locked symbols y: (rpps Frame or None, the decided frames (rows x period, symbol indices, each row starting at
    the unique word), the coherence per position (from the unique word on), rpps' candidate periods, len(y)). Runs on a
    Job's thread"""
    from rpps.analysis.framing import frames
    fr = frames.find(y, mod, max_lag=max(16, len(y) // 8))
    if fr is None:
        return None, None, None, frames.periods(y, max_lag=max(16, len(y) // 8), top=5), len(y)
    cut = frames.cut(y, fr)
    cut = cut / np.sqrt(np.mean(np.abs(cut) ** 2))
    idx = np.argmin(np.abs(cut[..., None] - points[None, None, :]), axis=-1)
    return fr, idx, np.roll(frames.coherence(y, fr.period), -fr.uw_start), [], len(y)


@plot("Frame Raster")
class FrameRaster(DSPPlot):
    """The selection's symbols wrapped at the period they repeat with (rpps.analysis.framing.frames): one frame a row
    starting at its unique word, each symbol colored by its decided value, so the unique word that marks each frame
    stands as a band of fixed columns and fixed fields show as stripes. Below, how coherent each position is from frame
    to frame (1: the same symbol every frame). The lock is followed block by block (rpps' Lock.follow: each block's
    symbols join the last's with none dropped or repeated, on the same rotation), and the last `symbols` of them kept,
    so periods longer than a block show. A gap between blocks, or a follow rpps calls stale (a slip is likely), starts
    the symbols over. A period is drawn once CONFIRM searches in a row find it, and kept until DROP in a row do not:
    one search's chance match does not flash a raster up, nor one miss take a real one away"""
    TITLE = "Frame Raster"
    CATEGORY = "Decoding"
    FEATURES = frozenset({LINE, IMAGE})
    ABOUT = About(
        data="The analysed signal's lock (rpps.sync.Lock) followed block by block, its symbols kept over contiguous "
             "blocks; the lag their products y[n] y*[n+P] are coherent at, the unique word, and the frames cut on it "
             "and turned to match it (rpps.analysis.framing.frames), in the background",
        shows="Frames (rows) by symbol position (columns), colored by the decided symbol, the unique word boxed; the "
              "coherence of each position; the period, the unique word's place and length",
        use=("Find a modem's frame length and unique word", "See fixed header fields and where the payload starts",
             "Prepare the frames for a code search (rpps.analysis.code)"),
        cost=45, # the shared lock (6) and a follow (6) a block, and the frame search over up to 200000 symbols (on its own thread)
    )
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("symbols", "Symbols", "int", default=200000, min=512, max=1000000, step=1024, reset=True, group="Frames",
                help="locked symbols kept from contiguous blocks: a period needs 8 frames in them (each search looks at "
                     "what is kept so far, so short periods show long before it is full)"),
        Setting("interval", "Analyse every", "number", default=0.0, min=0.0, max=60.0, step=0.5, hint="s of signal",
                group="Frames", help="seconds of signal between frame searches, 0 for every block (a long record's "
                                     "search costs more: search less often)"),
        Setting("frames", "Rows", "int", default=64, min=4, max=512, group="Display", help="frames drawn, the newest"),
        SETTING_CMAP.with_(default="hot"),
    )

    def reset(self):
        super().reset()
        self.job = Job("frame raster")
        self._baud = 0.0
        self.restart(None)

    def restart(self, key):
        """Start gathering over: another signal, modulation or rate (a followed lock's rate moving by a few ppm keeps it)"""
        self._key = key
        self._seq = None
        self.start_over()
        self.job.clear()
        self._runs = self.job.runs # the searches seen
        self._shown = None         # the result drawn: a confirmed period
        self._streak = []          # periods (None: none found) of the latest searches

    def start_over(self):
        """Drop the kept symbols (a gap, a slip): the next block starts a new chain of follows"""
        self.syms = np.zeros(0, np.complex128)
        self._chain = None   # the rpps Lock of the last block, followed onto the next
        self._pos = 0        # the baseband position of the next block's first sample
        self._since = np.inf # seconds of signal since the last frame search: the first comes at once

    def follow(self, lk, x: np.ndarray):
        """Join this block's symbols on to the kept ones (or start a chain on it)"""
        from rpps.errors import NoLock as RppsNoLock
        try:
            if self._chain is not None:
                nxt = self._chain.follow(x, at=self._pos, recheck=False)
                if nxt.stale: # a slip is likely: the symbols so far no longer line up with these
                    self.start_over()
                    nxt = None
            else:
                nxt = None
            if nxt is None:
                nxt = lk.rpps.update(x, recheck=False, at=self._pos)
            self._chain = nxt
            self.syms = np.concatenate((self.syms, np.asarray(nxt.symbols)))[-self.symbols:] # type: ignore
        except RppsNoLock: # too few symbols in the block, or not the next one
            self.start_over()
        self._pos += len(x)

    def confirm(self, res):
        """Take a new search's result: draw its period once CONFIRM searches in a row found it, drop the one drawn
        once DROP in a row did not"""
        P = res[0].period if res is not None and res[0] is not None else None
        self._streak = (self._streak + [P])[-max(CONFIRM, DROP):]
        same = lambda a, b: a is not None and b is not None and abs(a - b) <= max(1, 2e-3 * b)
        last = self._streak[-CONFIRM:]
        if len(last) == CONFIRM and all(same(q, P) for q in last):
            self._shown = res
        elif self._shown is not None:
            if same(P, self._shown[0].period):
                self._shown = res # still there: the newest frames
            elif len(self._streak) >= DROP and not any(same(q, self._shown[0].period) for q in self._streak[-DROP:]):
                self._shown = None

    def render(self):
        sel, lk, why = self.analyse()
        if lk is None:
            return self.empty([Axis(ylabel="Frame"), Axis(ylabel="Coherence")], sel, why)
        src = self.source
        key = (sel.key, lk.mod, lk.Fs) # type: ignore
        if key != self._key or abs(lk.baud - self._baud) > 1e-3 * lk.baud:
            self.restart(key)
            self._baud = lk.baud
        if src.seq != self._seq:
            if self._seq is not None and src.seq != self._seq + 1:
                self.start_over() # a gap: the symbols before it do not line up with the ones after
            self._seq = src.seq
            self.follow(lk, analyzer(src).block(sel)[0])
            self._since += len(src.samples) / src.fs
        if len(self.syms) >= 256 and self._since >= self.interval: # type: ignore
            if self.job.submit(find_frames, self.syms.copy(), lk.mod, np.asarray(lk.points)):
                self._since = 0.0
        readout = [*self.sel_readout(sel), ("Mod", lk.mod), ("Baud", fmt_hz(lk.baud).replace("Hz", "Bd"))]
        res = self.job.result
        if self.job.runs != self._runs:
            self._runs = self.job.runs
            self.confirm(res)
        if res is not None:
            readout.append(("Symbols", str(res[4])))
        if self._shown is not None:
            res = self._shown
        if res is None or res[0] is None or self._shown is None:
            if res is not None and res[0] is not None:
                readout.append(("Frames", f"period {res[0].period} found, checking it repeats"))
            elif res is not None:
                full = res[4] >= self.symbols # type: ignore
                readout.append(("Frames", f"none found in {res[4]} symbols" + ("" if full else
                                f", gathering up to {self.symbols} (a period needs 8 frames)"))) # type: ignore
            readout += self.job.readout()
            rows = [TableRow(f"L{k}", [f"L{k}", str(lag), f"{c:.2f}"]) for k, (lag, c) in enumerate(res[3] if res else [], 1)]
            return Frame([Axis(ylabel="Frame"), Axis(ylabel="Coherence")], title=self.TITLE, readout=readout,
                         table=Table(["", "Lag (symbols)", "Correlation"], rows) if rows else None)
        fr, idx, prof, _, _ = res
        P = fr.period
        shown = idx[-self.frames:] # type: ignore
        M = max(2, len(lk.points))
        im = (shown * (255 // (M - 1))).astype(np.uint8)[::-1] # the newest frame on top
        uw = Band(0.0, float(fr.uw_length), GREEN, 0.25, "UW") # each row starts at the unique word
        axes = [
            Axis(xmin=0.0, xmax=float(P), ymin=0.0, ymax=float(len(shown)), xlabel="Symbol", ylabel="Frame",
                 image=Image(im, cmap=self.cmap), bands=[uw]), # type: ignore
            Axis(xmin=0.0, xmax=float(P), ymin=0.0, ymax=1.1, xlabel="Symbol", ylabel="Coherence",
                 traces=[Trace(np.asarray(prof), np.arange(P) + 0.5, color=YELLOW, name="coherence")],
                 markers=[Marker(0.0, 0.5, "", RED, kind="hline")],
                 bands=[Band(0.0, float(fr.uw_length), GREEN, 0.15)]),
        ]
        readout += [("Period", f"{P} symbols ({fmt_time(P / lk.baud)})"),
                    ("Unique word", f"{fr.uw_length} symbols at {fr.uw_start}"),
                    ("Coherence", f"{fr.coherence:.2f} (others {fr.floor:.2f})"), ("Frames", str(fr.frames))]
        readout += self.job.readout()
        word = " ".join(str(int(v)) for v in idx[0][:min(fr.uw_length, 64)])
        rows = [TableRow("uw", ["Unique word", word + (" ..." if fr.uw_length > 64 else "")])]
        return Frame(axes, title=self.TITLE, readout=readout, table=Table(["", "Symbols (decided index)"], rows))
