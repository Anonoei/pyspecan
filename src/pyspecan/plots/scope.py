"""Oscilloscope: the samples against time, triggered or rolling

Triggered modes (auto / normal / single) keep the samples carried from earlier blocks, so a
screen may be longer than one block, and draw up to `overlay` triggered sweeps from each block
on top of each other (older ones faded), so little of what was read goes unseen.

Roll mode is a strip chart: every block is reduced to a min / max envelope per screen column
and pushed in from the right, so every sample is shown at a fixed drawing cost.
"""
from dataclasses import replace

import numpy as np

from ..measure import trigger
from .base import About, Plot, plot
from .frame import BLUE, GREEN, RED, YELLOW, Axis, Frame, Marker, Trace, fmt_time
from .freq import fmt_hz, freq_text, hz
from .reduce import COLS, envelope
from .settings import Setting

MAX_SPAN = 1 << 22  # most samples one screen holds, bounds the carried history

CHANNELS = ("I/Q", "I", "Q", "Mag", "Phase")
MODES = ("auto", "normal", "single", "roll")
_PREFIX = {"n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3}

def parse_time(value) -> float:
    """'10u', '2.5ms', '1e-3', '' -> seconds, 0 for blank or 'auto'"""
    s = str(value).strip().lower().removesuffix("s").strip()
    if s in ("", "auto", "0"):
        return 0.0
    mul = 1.0
    if s[-1] in _PREFIX:
        s, mul = s[:-1], _PREFIX[s[-1]]
    try:
        v = float(s) * mul
    except ValueError:
        raise ValueError(f"{value!r} is not a time, use e.g. 10u, 2m, 0.5") from None
    if v < 0:
        raise ValueError("time must not be negative")
    return v

def time_text(value) -> str:
    """coerce for text settings holding a time, blank and 'auto' stay as given"""
    parse_time(value)
    return str(value).strip()

def _per_div(value) -> str:
    s = str(value).strip().lower()
    if s in ("", "auto"):
        return "auto"
    if float(s) <= 0:
        raise ValueError("per division must be positive")
    return s

def components(x: np.ndarray, channel: str) -> list[tuple[str, np.ndarray, str]]:
    """(name, values, color) of what `channel` shows"""
    if channel == "I/Q":
        return [("i", x.real, YELLOW), ("q", x.imag, BLUE)]
    if channel == "I":
        return [("i", x.real, YELLOW)]
    if channel == "Q":
        return [("q", x.imag, BLUE)]
    if channel == "Mag":
        return [("mag", np.abs(x), GREEN)]
    if channel == "Phase":
        return [("phase", np.angle(x), GREEN)]
    raise ValueError(f"unknown channel {channel!r}")

@plot("Scope")
class Scope(Plot):
    TITLE = "Scope"
    CATEGORY = "Time domain"
    ABOUT = About(
        data='The raw samples, carried across blocks, triggered on a level crossing of I, Q or the '
             'magnitude (or rolling)',
        shows='Amplitude against time: I and Q (or magnitude, phase), older triggered sweeps fading; the '
              'trigger level is a line to drag',
        use=(
            'Look at waveforms and modulation envelopes',
            'Trigger on bursts to capture their shape',
            'Roll mode: a strip chart of a slowly changing signal',
        ),
        cost=0.58,
    )
    SETTINGS = (
        Setting("channel", "Show", "select", default="I/Q", options=CHANNELS, reset=True, group="Timebase"),
        Setting("time_div", "Time / div", "text", default="auto", coerce=time_text, hint="auto, 10u, 2m", reset=True,
                help="scope time per division, 10 per screen ('auto': one FFT)", group="Timebase"),
        Setting("v_div", "Value / div", "text", default="auto", coerce=_per_div, hint="auto", group="Timebase"),
        Setting("trig_mode", "Trigger", "select", default="auto", options=MODES, reset=True,
                help="scope trigger mode, roll is an untriggered strip chart", group="Trigger"),
        Setting("trig_src", "Trig source", "select", default="I", options=trigger.SOURCES, group="Trigger"),
        Setting("trig_edge", "Trig edge", "select", default="rising", options=trigger.EDGES, group="Trigger"),
        Setting("trig_level", "Trig level", "number", default=0.0, step=0.05, help="scope trigger level", group="Trigger"),
        Setting("trig_pos", "Pre-trigger %", "number", default=10.0, min=0, max=100, step=5, group="Trigger"),
        Setting("holdoff", "Holdoff", "text", default="", coerce=time_text, hint="0", group="Trigger", advanced=True),
        Setting("overlay", "Overlay", "int", default=8, min=1, max=64, hint="sweeps per refresh", group="Timebase", advanced=True),
    )

    def reset(self):
        self.buf = np.empty(0, dtype=np.complex64) # carried samples (triggered), or the last screen (roll, fine timebase)
        self.seen = -2      # source tick last read
        self.epoch = None   # source epoch last read
        self.last: Frame | None = None
        self.frozen = False # single: triggered once, holding
        self.y_max = 0.0
        self.env: dict[str, np.ndarray] = {} # roll: (2, COLS) min / max per component
        self.filled = 0     # roll: columns holding data
        self.pending = np.empty(0, dtype=np.complex64) # roll: samples short of a column

    def changed(self, key):
        if key.startswith("trig_") or key == "holdoff":
            self.frozen = False # any trigger change re-arms single

    # --- geometry --- #
    def geometry(self) -> tuple[float, int, int, int]:
        """(fs, samples per screen, samples before the trigger, holdoff samples)"""
        fs = self.source.fs or 1.0
        td = parse_time(self.time_div)
        n = int(round(td * 10 * fs)) if td > 0 else self.source.nfft
        n = min(max(n, 2), MAX_SPAN)
        pre = min(int(round(n * self.trig_pos / 100)), n - 1)
        return fs, n, pre, int(round(parse_time(self.holdoff) * fs))

    def _new_samples(self) -> np.ndarray | None:
        """The block not read yet, None when it was. History is dropped when blocks are not adjacent"""
        src = self.source
        if src.seq == self.seen and src.epoch == self.epoch:
            return None
        if src.epoch != self.epoch or src.seq != self.seen + 1:
            self.buf, self.pending = self.buf[:0], self.pending[:0]
            self.env, self.filled = {}, 0
        self.seen, self.epoch = src.seq, src.epoch
        return np.asarray(src.samples)

    # --- render --- #
    def render(self):
        new = self._new_samples()
        if self.trig_mode == "roll":
            return self._roll(new)
        return self._triggered(new)

    def _y_range(self, values) -> tuple[float, float]:
        if self.channel == "Phase":
            return -np.pi, np.pi
        if self.v_div != "auto":
            v = float(self.v_div)
            return (0.0, 10*v) if self.channel == "Mag" else (-5*v, 5*v)
        for y in values:
            if len(y):
                self.y_max = max(self.y_max, float(np.max(np.abs(y))))
        v = self.y_max or 1.0
        return (0.0, v) if self.channel == "Mag" else (-v, v)

    def _frame(self, axis: Axis, readout) -> Frame:
        return Frame([axis], title=self.TITLE, readout=readout)

    def _triggered(self, new):
        fs, n, pre, hold = self.geometry()
        if self.frozen and self.last is not None:
            return self.last
        if new is not None:
            keep = n + hold # what a trigger not complete yet may still need
            self.buf = np.concatenate((self.buf[-keep:], new)) if len(self.buf) else new
        buf = self.buf
        span = [("Span", fmt_time(n / fs))]
        if len(buf) < n:
            return self._frame(Axis(xmin=-pre/fs, xmax=(n-pre)/fs, xfmt="time", xlabel="Time"),
                               [("Trig", "filling"), *span])

        post = n - pre
        spacing = n + hold
        start = max(0, len(buf) - ((self.overlay + 1) * spacing + n)) # older triggers would not be drawn
        sig = trigger.signal(buf[start:], self.trig_src)
        trigs = trigger.find(sig, self.trig_level, self.trig_edge, spacing) + start
        trigs = trigs[(trigs - pre >= 0) & (trigs + post <= len(buf))][-self.overlay:]

        if not len(trigs):
            if self.trig_mode != "auto":
                if self.last is None:
                    return self._frame(Axis(xmin=-pre/fs, xmax=post/fs, xfmt="time", xlabel="Time"),
                                       [("Trig", "armed"), *span])
                return replace(self.last, readout=[("Trig", "armed"), *span])
            trigs, state = np.array([float(len(buf) - post)]), "auto"
        else:
            state = "triggered"

        traces, shown = [], []
        for age, t in enumerate(trigs[::-1]): # newest first, drawn last
            i0 = int(np.ceil(t - pre))
            x = (np.arange(i0, i0 + n) - t) / fs
            alpha = 1.0 if age == 0 else max(0.08, 0.5 * (1 - age / len(trigs)))
            for name, y, color in components(buf[i0:i0 + n], self.channel):
                shown.append(y)
                xs, ys = envelope(x, y)
                traces.insert(0, Trace(ys, xs, color=color, name=f"{name}{age}", alpha=alpha, width=1.5 if age == 0 else 1.0))
        ymin, ymax = self._y_range(shown)
        markers = [Marker(0.0, kind="vline", color=RED)]
        if self.channel != "Phase":
            markers.append(Marker(0.0, self.trig_level, label="T", color=RED, kind="hline", edit="trig_level"))
        if self.trig_mode == "single" and state == "triggered":
            self.frozen = True
            state = "stopped"
        self.last = self._frame(Axis(
            xmin=-pre/fs, xmax=post/fs, ymin=ymin, ymax=ymax, xfmt="time", xlabel="Time",
            traces=traces, markers=markers,
        ), [("Trig", state), *span, ("Sweeps", str(len(trigs)))])
        return self.last

    def _roll(self, new):
        fs, n, _, _ = self.geometry()
        spc = n / COLS # samples per column
        if spc <= 1: # fine timebase: the last screen as it is
            if new is not None:
                self.buf = np.concatenate((self.buf, new))[-n:]
            comps = components(self.buf, self.channel)
            x = (np.arange(len(self.buf)) - (len(self.buf) - 1)) / fs
            traces = [Trace(y, x, color=c, name=name) for name, y, c in comps if len(y)]
            shown = [y for _, y, _ in comps]
        else:
            if new is not None:
                data = np.concatenate((self.pending, new)) if len(self.pending) else new
                ncols = int(len(data) / spc)
                if ncols:
                    first = max(0, ncols - COLS) # columns that would scroll straight off are not computed
                    edges = (np.arange(first, ncols + 1) * spc).astype(np.int64)
                    starts = edges[:-1] - edges[0]
                    for name, y, _ in components(data[edges[0]:edges[-1]], self.channel):
                        mn, mx = np.minimum.reduceat(y, starts), np.maximum.reduceat(y, starts)
                        env = self.env.get(name)
                        if env is None:
                            env = self.env[name] = np.zeros((2, COLS), dtype=np.float64)
                        k = min(ncols, COLS)
                        env[:, :-k] = env[:, k:].copy()
                        env[0, -k:], env[1, -k:] = mn[-k:], mx[-k:]
                    self.filled = min(COLS, self.filled + ncols)
                    self.pending = data[edges[-1]:].copy()
                else:
                    self.pending = data.copy()
            f = self.filled
            x = (np.arange(COLS - f, COLS) - (COLS - 1)) * spc / fs
            traces, shown = [], []
            for name, _, color in components(np.zeros(1, np.complex64), self.channel):
                env = self.env.get(name)
                if env is None or not f:
                    continue
                shown.append(env[:, -f:].ravel())
                traces.append(Trace(env[:, -f:].T.ravel(), np.repeat(x, 2), color=color, name=name))
        ymin, ymax = self._y_range(shown)
        return self._frame(Axis(
            xmin=-n/fs, xmax=0.0, ymin=ymin, ymax=ymax, xfmt="time", xlabel="Time", traces=traces,
        ), [("Trig", "roll"), ("Span", fmt_time(n / fs))])

@plot("Frequency vs Time")
class FreqVsTime(Plot):
    """Instantaneous frequency (an FM discriminator): the phase step between samples, as an offset from the
    tuned frequency. Shows FM / FSK deviation, chirps and frequency hops"""
    TITLE = "Frequency vs Time"
    CATEGORY = "Analog demodulation"
    ABOUT = About(
        data='The latest samples through an FM discriminator (the phase step between samples), optionally'
             ' smoothed',
        shows='Instantaneous frequency offset against time; mean, deviation and RMS',
        use=('See FSK symbols and frequency hops', 'Measure chirps and how a synthesizer settles'),
        cost=0.06,
    )
    SETTINGS = (
        Setting("count", "Samples", "int", default=4096, min=2, step=256, help="samples to plot", group="Timebase"),
        Setting("smooth", "Smoothing", "int", default=1, min=1, max=4096, help="samples averaged (moving average), 1 for none",
                group="Display"),
        Setting("fspan", "Freq span", "text", default="", coerce=freq_text, hint="sample rate",
                help="height of the frequency axis, centered on the tuned frequency", group="Display"),
    )

    def render(self):
        samps = self.source.samples[-self.count:]
        if len(samps) < 2:
            return None
        fs = self.source.fs or 1.0
        f = np.angle(samps[1:] * np.conj(samps[:-1])) * (fs / (2 * np.pi))
        if self.smooth > 1 and len(f) > self.smooth:
            f = np.convolve(f, np.full(self.smooth, 1.0 / self.smooth), "valid")
        t = np.arange(len(f)) / fs
        x, y = envelope(t, f) # a long trace as a min / max envelope
        span = hz(self.fspan, fs) or fs
        return Frame([Axis(
            xmin=0.0, xmax=len(samps) / fs, xfmt="time", ymin=-span / 2, ymax=span / 2, yfmt="freq",
            xlabel="Time", ylabel="Offset", traces=[Trace(y, x, color=GREEN, name="freq")],
        )], title=self.TITLE, readout=[
            ("Mean", fmt_hz(float(f.mean()))), ("Deviation", fmt_hz(float(f.max() - f.min()) / 2)),
            ("RMS", fmt_hz(float(f.std()))),
        ])
