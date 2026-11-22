"""What a signal is: Waveform ID (tones, OFDM, bursts, envelope, constellation or FSK, on rpps' tests) and Signal
Profile (every step that processes it, as far as rpps' analysis can tell). Both run in the background (`common.Job`):
their searches take a second or more"""
import numpy as np

from ..base import About, plot
from ..frame import BLUE, GREEN, LINE, YELLOW, Axis, Band, Frame, Table, TableRow, Trace, fmt_time
from ..freq import fmt_hz
from ..settings import Setting
from .analyzer import NoLock, analyzer
from .common import SETTING_DECAY, DSPPlot, Job, welch

SPECTRUM_BINS = 512


def identify(x: np.ndarray, Fs: float, syms: np.ndarray | None):
    """rpps' waveform tests on the baseband x, then what fits its kind: the constellation by its cumulants (a single
    carrier, from the locked symbols) or the FSK parameters (a constant envelope). Runs on a Job's thread"""
    from rpps.analysis.modulation import cumulants, fsk
    from rpps.analysis.spectrum import waveform
    w = waveform.classify(x, Fs)
    cm = cumulants.classify(syms)[:3] if syms is not None and len(syms) >= 256 and w.kind is None else None
    fk = fsk.analyze(x, Fs) if w.kind == "constant envelope" else None
    return w, cm, fk


def verdict(w, cm, fk) -> str:
    """In a few words, what the tests say it is, and when it comes in bursts their period"""
    what = _kind(w, cm, fk)
    if w.bursts is not None:
        every = f" every {fmt_time(w.bursts.period)}" if w.bursts.period else ""
        return f"{what}, in bursts{every}"
    return what


def _kind(w, cm, fk) -> str:
    if w.kind == "tones":
        return "tones" if len(w.tones.lines) > 1 else "an unmodulated carrier"
    if w.kind == "ofdm":
        return "OFDM" + (f" ({w.ofdm.systems[0][0]})" if w.ofdm.systems else "")
    if w.kind == "constant envelope":
        return f"{fk.name}" if fk is not None and fk.M is not None else "constant envelope (FM, FSK or CPM)"
    if cm:
        return f"{cm[0].name}, a single carrier"
    return "not recognized"


@plot("Waveform ID")
class WaveformID(DSPPlot):
    """What kind of signal the selection is, by rpps' tests and why each holds: tones (nearly all the power in a few
    lines), OFDM (the cyclic prefix correlating at the useful symbol length, and the system those fit), bursts (the
    power switching on and off, and its period), the envelope statistic; then for a constant envelope the FSK
    parameters, for a single carrier the constellation its symbols' higher order cumulants fit best"""
    TITLE = "Waveform ID"
    CATEGORY = "Channel and signal analysis"
    FEATURES = frozenset({LINE})
    ABOUT = About(
        data="The analysed signal (the Analysis settings, or a box clicked on the signals marker) shifted to 0 Hz and "
             "filtered, all of the block; rpps' waveform tests (rpps.analysis.spectrum.waveform), then its cumulants "
             "(the locked symbols) or FSK analysis, in the background",
        shows="A table of each test and what it found, what the signal is in a few words, and its spectrum at baseband",
        use=("Tell what an unknown signal is before choosing how to demodulate it",
             "Name an OFDM system from its subcarrier spacing and cyclic prefix",
             "Find a TDMA / TDD signal's frame period"),
        cost=11, # the analysis included (on its own thread)
    )
    SETTINGS = DSPPlot.SETTINGS + (SETTING_DECAY.with_(help="how much of the earlier blocks' spectrum stays"),)

    def reset(self):
        super().reset()
        self.job = Job("waveform id")
        self._for = None
        self.spec: np.ndarray | None = None

    def render(self):
        if not len(self.source.samples):
            return None
        an = analyzer(self.source)
        sel = an.selection(self.dsp_freq, self.dsp_bw) # type: ignore
        if sel is None:
            return Frame([Axis(xfmt="freq", ylabel="dB")], title=self.TITLE, readout=[("Signal", "none found")])
        if sel.key != self._for:
            self._for, self.spec = sel.key, None
            self.job.clear()
        x, Fs = an.block(sel)
        res = self.job.result
        lock, why = None, ""
        if res is None or res[0].kind is None: # a single carrier, or not known yet: its symbols tell the constellation
            try:
                lock = an.lock(sel, self.dsp_mod, self.dsp_baud) # type: ignore
            except NoLock as e:
                why = str(e)
        if len(x) >= 256:
            self.job.submit(identify, np.array(x), Fs, None if lock is None else np.array(lock.syms))
        axes = [self.spectrum_axis(x, Fs, sel.freq)]
        readout = self.sel_readout(sel)
        rows = []
        if res is not None:
            w, cm, fk = res
            readout.append(("Is", verdict(w, cm, fk)))
            rows = self.rows(w, cm, fk)
        if lock is not None:
            rows.append(TableRow("lock", ["Lock", f"{lock.mod} at {fmt_hz(lock.baud).replace('Hz', 'Bd')}, Es/N0 {lock.esn0:.1f} dB"]))
        elif why and (res is None or res[0].kind is None):
            rows.append(TableRow("lock", ["Lock", why]))
        readout += self.job.readout()
        return Frame(axes, title=self.TITLE, readout=readout, table=Table(["Test", "Result"], rows))

    def spectrum_axis(self, x: np.ndarray, Fs: float, f0: float) -> Axis:
        n = SPECTRUM_BINS if len(x) >= SPECTRUM_BINS else 1 << max(4, int(np.log2(max(len(x), 16))) - 1)
        p = welch(x, n)
        if self.spec is None or len(self.spec) != n:
            self.spec = p
        else:
            self.spec = self.decay * self.spec + (1 - self.decay) * p # type: ignore
        db = 10 * np.log10(np.maximum(self.spec, 1e-30))
        f = f0 + (np.arange(n) - n // 2) * (Fs / n)
        top = float(np.ceil(db.max() / 10) * 10 + 5)
        return Axis(xmin=f[0], xmax=f[-1], xfmt="freq", ymin=top - 80, ymax=top, ylabel="dB",
                    traces=[Trace(db, f, color=YELLOW, name="spectrum")])

    @staticmethod
    def rows(w, cm, fk) -> list[TableRow]:
        out = [TableRow("tones", ["Tones", str(w.tones) if w.tones is not None else "none: the power is not in a few lines"])]
        if w.tones is None:
            o = w.ofdm
            out.append(TableRow("ofdm", ["OFDM", str(o) if o is not None else "no cyclic prefix correlation"]))
            if o is not None and len(o.systems) > 1:
                out.append(TableRow("", ["", "also fits: " + ", ".join(name for name, _ in o.systems[1:4])]))
            out.append(TableRow("bursts", ["Bursts", str(w.bursts) if w.bursts is not None else "steady (or too weak to tell)"]))
        if w.envelope is not None:
            out.append(TableRow("env", ["Envelope", f"E|x|^4/E|x|^2^2 = {w.envelope:.2f} (1 constant, 1.3-1.7 filtered PSK, "
                                                    "2 Gaussian: noise, OFDM, many carriers)"]))
        if fk is not None:
            out.append(TableRow("fsk", ["FSK", str(fk)]))
        if cm:
            best = cm[0]
            es = "" if best.esn0_db is None else f", Es/N0 {best.esn0_db:.1f} dB"
            out.append(TableRow("cum", ["Cumulants", f"{best.name} (distance {best.distance:.3f}{es})"]))
            out.append(TableRow("", ["", "next: " + ", ".join(f"{m.name} {m.distance:.3f}" for m in cm[1:])]))
        return out


MAX_CAPTURE = 1 << 24 # samples a profile's capture holds at most (128 MB)
MARK = {"found": "", "guess": "?", "unsolved": "!"}

def run_profile(x: np.ndarray, fs: float, cf: float, signals, blind: bool):
    """rpps' profiles of the capture x (rpps.analysis.profile), signals: a list of rpps Signal or None for every
    signal it finds. Runs on a Job's thread"""
    from rpps.analysis import profile
    from rpps.source import Memory
    block = 16384
    return profile(Memory(x, Fs=fs, cf=cf), signals=signals, blocks=len(x) // block + 1, block=block, blind=blind)


@plot("Signal Profile")
class SignalProfile(DSPPlot):
    """Every step that processes a signal, as far as rpps' analysis tells (rpps.analysis.profile): its channel, rate and
    modulation, timing, carrier, then the code, its bit map and framing, or a profile that decodes it. A step is found
    (a definition covers it), a guess (?, a blind find) or unsolved (!), which ends the list with its likeliest
    candidates. It captures `capture` seconds of contiguous blocks, then profiles them in the background (seconds; the
    blind tools tens of seconds a signal); "run" captures and profiles again"""
    TITLE = "Signal Profile"
    CATEGORY = "Decoding"
    FEATURES = frozenset({LINE})
    ACTIONS = ("run",)
    ABOUT = About(
        data="Contiguous blocks captured, then each signal's chain (channel, acquisition, matched filter, carrier, FEC "
             "acquisition) run over the capture by rpps.analysis.profile, in the background",
        shows="The steps that process the selection (or every signal found), numbered, with what is left unsolved and "
              "its likeliest candidates; the capture's spectrum with the profiled signals boxed",
        use=("Work out how to receive an unknown signal: rate, modulation, code, framing",
             "See which shipped profile decodes a signal (then decode it in the Decode plot)"),
        cost=0.02, # capturing, a block; the profile then runs once a capture on its own thread (seconds)
    )
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("capture", "Capture (s)", "number", default=0.25, min=0.01, max=10.0, step=0.05, reset=True, group="Profile",
                help="seconds of contiguous samples profiled (the chain needs thousands of symbols to find a code)"),
        Setting("which", "Signals", "select", default="selection", options=("selection", "all"), reset=True, group="Profile",
                help="the analysed signal, or every signal the capture's survey finds"),
        Setting("blind", "Blind FEC search", "check", default=False, reset=True, group="Profile",
                help="where no definition fits, rpps' blind tools look for the code (tens of seconds a signal)"),
        Setting("repeat", "Repeat", "check", default=False, group="Profile", help="capture and profile again when done"),
    )

    def reset(self):
        super().reset()
        self.job = Job("signal profile")
        self.start_capture()

    def start_capture(self):
        self.parts: list[np.ndarray] = []
        self.have = 0
        self._seq = None
        self.capturing = True
        self.spec = None # the capture's spectrum and its frequencies
        self.profiled: list = [] # [(lo, hi)] absolute Hz of the signals the run profiles

    def act(self, action):
        if action == "run":
            self.job.clear()
            self.start_capture()
        else:
            super().act(action)

    def _capture(self) -> bool:
        """Add the block to the capture (a gap starts it over), True when it is long enough"""
        src = self.source
        key = (src.epoch, src.fs, src.cf)
        if self._seq is not None and (src.seq != self._seq[0] + 1 or key != self._seq[1]):
            self.parts, self.have = [], 0
        if self._seq is None or src.seq != self._seq[0]:
            x = np.asarray(src.samples, dtype=np.complex64)
            self.parts.append(x.copy())
            self.have += len(x)
        self._seq = (src.seq, key)
        return self.have >= min(self.capture * src.fs, MAX_CAPTURE) # type: ignore

    def render(self):
        if not len(self.source.samples):
            return None
        src = self.source
        readout = []
        if self.capturing:
            sel = None
            if self.which == "selection": # type: ignore
                sel = analyzer(src).selection(self.dsp_freq, self.dsp_bw) # type: ignore
                if sel is None:
                    return Frame([Axis(xfmt="freq", ylabel="dB")], title=self.TITLE, readout=[("Signal", "none found")])
            if self._capture():
                x = np.concatenate(self.parts)[:MAX_CAPTURE]
                self.parts = []
                self.capturing = False
                self.spec = self.spectrum(x[:1 << 20])
                self.profiled = [] if sel is None else [(sel.freq - sel.width / 2, sel.freq + sel.width / 2)]
                self.job.submit(run_profile, x, src.fs, src.cf, None if sel is None else [sel.signal], self.blind)
            else:
                want = min(self.capture * src.fs, MAX_CAPTURE) # type: ignore
                readout.append(("Status", f"capturing {100 * self.have / want:.0f}% of {fmt_time(want / src.fs)}"))
                if not self.job.result: # the block meanwhile (a profile on screen keeps its capture's spectrum)
                    self.spec = self.spectrum(np.asarray(src.samples))
        elif self.repeat and not self.job.busy and self.job.result is not None: # type: ignore
            self.start_capture()
        profiles = self.job.result or []
        rows = []
        for k, p in enumerate(profiles, 1):
            head = p.profile_name and f"profile {p.profile_name}" or ("solved" if p.solved else "UNSOLVED")
            rows.append(TableRow(f"S{k}", [f"S{k}", "", "", f"{p.name}: {head}"]))
            for i, st in enumerate(p.steps, 1):
                rows.append(TableRow("", ["", f"{i}{MARK.get(st.status, '')}", st.kind, st.what + (f" ({st.note})" if st.note else "")]))
                for name, z, wt in st.candidates:
                    rows.append(TableRow("", ["", "", "", f"{wt * 100:.1f}%  z={z:.1f}  {name}"]))
        if profiles:
            done = sum(1 for p in profiles if p.solved or p.profile_name)
            readout.append(("Solved", f"{done} of {len(profiles)}"))
            if not self.profiled: # every signal: box what the capture's survey found
                self.profiled = [(p.signal.freq - p.signal.width / 2, p.signal.freq + p.signal.width / 2)
                                 for p in profiles if p.signal is not None]
        elif not self.capturing and not self.job.busy and not self.job.error:
            readout.append(("Status", "no signal to profile"))
        readout += self.job.readout()
        return Frame([self.axis()], title=self.TITLE, readout=readout, table=Table(["", "#", "Step", "What"], rows))

    def spectrum(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(dB, absolute Hz) of x's averaged spectrum"""
        n = 1024 if len(x) >= 2048 else max(16, 1 << int(np.log2(max(len(x), 32)) - 1))
        return 10 * np.log10(np.maximum(welch(x, n), 1e-30)), self.source.cf + (np.arange(n) - n // 2) * (self.source.fs / n)

    def axis(self) -> Axis:
        if self.spec is None:
            lo, hi = self.source.freq_range()
            return Axis(xmin=lo, xmax=hi, xfmt="freq", ylabel="dB")
        db, f = self.spec
        top = float(np.ceil(db.max() / 10) * 10 + 5)
        return Axis(xmin=f[0], xmax=f[-1], xfmt="freq", ymin=top - 80, ymax=top, ylabel="dB",
                    traces=[Trace(db, f, color=BLUE, name="capture")],
                    bands=[Band(lo, hi, GREEN, 0.2, f"S{k}") for k, (lo, hi) in enumerate(self.profiled, 1)])
