import numpy as np

from ..measure import trigger, windows
from .base import About, plot
from .frame import BLUE, GREEN, RED, Axis, Band, Frame, Marker, Trace, fmt_time
from .freq import FreqPlot, RefMixin, TraceMixin, _ref_level, to_psd
from .reduce import envelope
from .settings import Setting, parse_time, time_text

FREE_RUN, GATED = "free run", "gated"

class GateMixin:
    """A gated spectrum: only the frames inside the gate count, so a bursty signal's spectrum is not diluted by the
    time it is off (and the off time's noise is not averaged in). The gate opens on the samples' power (dBFS, smoothed
    over nfft / 16) reaching a level: `gate_delay` after it rises, for `gate_length` (blank: until it falls). The frames
    are the back to back FFT frames that fit inside each opening of this block; a block with none leaves the traces as
    they were, like an analyzer waiting for its trigger. A time axis under the spectrum shows the power, the level (a
    line to drag) and the open spans"""
    SETTINGS = (
        Setting("trig_mode", "Trigger", "select", default=FREE_RUN, options=(FREE_RUN, GATED), reset=True, group="Trigger",
                help="free run: every frame; gated: only the frames while the power is over the gate level"),
        Setting("gate_level", "Gate level", "text", default="auto", coerce=_ref_level, hint="auto, dBFS", group="Trigger",
                help="power (dBFS) that opens the gate, 'auto' halfway between the floor and the peaks of each block"),
        Setting("gate_delay", "Gate delay", "text", default="", coerce=time_text, hint="0, 10u, 2m", group="Trigger",
                help="the gate opens this long after the power rises (skip a burst's ramp or preamble)"),
        Setting("gate_length", "Gate length", "text", default="", coerce=time_text, hint="while over", group="Trigger",
                help="how long it stays open, blank while the power is over the level"),
        Setting("gate_view", "Show gate", "check", default=True, group="Trigger", help="the power against time under the spectrum"),
    )

    @property
    def gated(self) -> bool:
        return self.trig_mode == GATED # type: ignore

    def gate_rows(self) -> np.ndarray:
        """(k, nfft) unsmoothed psd rows of the frames inside the gate in this block; the gate's state for gate_axis"""
        src = self.source # type: ignore
        x = np.asarray(src.samples)
        n, fs = src.nfft, src.fs
        self._gate = None
        if len(x) < n:
            return np.empty((0, n))
        p = trigger.power_db(x, max(1, n // 16))
        level = trigger.auto_level(p) if self.gate_level == "auto" else float(self.gate_level) # type: ignore
        spans = trigger.gate_spans(p, level, int(round(parse_time(self.gate_delay) * fs)), # type: ignore
                                   int(round(parse_time(self.gate_length) * fs))) # type: ignore
        starts = trigger.frame_starts(spans, n)
        self._gate = (p, level, spans, len(starts))
        if not len(starts):
            return np.empty((0, n))
        win = windows.window(self.window, n) # type: ignore
        spectra = np.fft.fftshift(np.fft.fft(x[starts[:, None] + np.arange(n)] * win, axis=1), axes=1)
        return to_psd(spectra, fs, self.window, self.unit, self.cal_db, self.ext_gain) # type: ignore

    def gate_readout(self) -> list[tuple[str, str]]:
        if self._gate is None:
            return [("Gate", "waiting for samples")]
        _, level, spans, frames = self._gate
        state = f"{frames} frames in {len(spans)} openings" if frames else (
            "waiting: open shorter than an FFT" if spans else "waiting: never over the level")
        return [("Gate", state), ("Gate level", f"{level:.1f} dBFS")]

    def gate_axis(self) -> Axis | None:
        """The block's power against time, the level to drag and the open spans"""
        if not self.gate_view or self._gate is None: # type: ignore
            return None
        p, level, spans, _ = self._gate
        fs = self.source.fs # type: ignore
        t = np.arange(len(p)) / fs
        xs, ys = envelope(t, p)
        top = max(float(np.max(p)), level) + 5.0
        btm = min(float(np.percentile(p, 1)), level) - 5.0
        return Axis(xmin=0.0, xmax=len(p) / fs, ymin=btm, ymax=top, xfmt="time", xlabel="Time", ylabel="dBFS",
                    traces=[Trace(ys, xs, color=BLUE, name="gate power", width=1.0)],
                    markers=[Marker(0.0, level, "gate", RED, kind="hline", edit="gate_level")],
                    bands=[Band(a / fs, b / fs, GREEN, 0.2) for a, b in spans[:200]])

    def gate_title(self) -> str:
        return f" (gated, {fmt_time(len(self._gate[0]) / self.source.fs)} block)" if self._gate is not None else " (gated)" # type: ignore


@plot("PSD")
class PSD(GateMixin, RefMixin, TraceMixin, FreqPlot):
    """Power spectral density as an analyzer's traces: each of them clear/write, average, max / min hold, view or
    blank (see TraceMixin), every one sees every frame of the block (the persistence plot is the realtime view).
    Markers and measurements read the marker trace at full resolution, only the drawn traces go through the detector.
    Gated (see GateMixin), only the frames while a burst is on count"""
    TITLE = "PSD"
    CATEGORY = "Spectrum"
    ABOUT = About(
        data='The block cut into frames (FFT size, window), each transformed and scaled to power per Hz '
             '(or dBm, dBFS) and smoothed by the VBW; four traces fold every frame in, each its own way '
             '(clear/write, average, max hold, min hold, view, blank); the detector reduces the bins to the display points. '
             'Gated: only the frames while the power is over the gate level',
        shows='Level against frequency across the tuned span: trace 1 (yellow, clear/write), 2 (red, max hold), '
              '3 (blue, min hold) and 4 (green, blank) by default, a stored reference (grey), markers and their '
              'table; with trace math, marker trace - ref on an axis of its own; gated, the power against time with '
              'the gate level and the open spans',
        use=(
            'Find and measure signals: peak, channel power, ACPR, occupied bandwidth, harmonics, TOI',
            'Average a noisy trace while a max hold catches what comes and goes',
            'Compare against a stored reference before and after a change (store ref, trace math)',
            "Check a limit (the limit marker's pass / fail)",
            "Gated: a burst's spectrum alone (TDMA, radar, packet radio), without the noise between bursts",
        ),
        cost=1.0,
    )
    SETTINGS = FreqPlot.SETTINGS + TraceMixin.SETTINGS + RefMixin.SETTINGS + GateMixin.SETTINGS

    def reset(self):
        super().reset()
        self.reset_traces()
        self.last_shown = None
        self._gate = None

    def spectrum_rows(self) -> np.ndarray:
        """The block's unsmoothed psd rows: every swept frame, or gated the frames inside the gate"""
        return self.gate_rows() if self.gated else self.psd_rows("swept", smooth=False)

    def render(self):
        raw = self.spectrum_rows()
        if len(raw):
            self.fold(raw)
        elif not self.gated or self.last is None:
            if self.gated and self._gate is not None: # nothing through the gate yet: show why
                fmin, fmax = self.source.freq_range()
                ax = Axis(xmin=fmin, xmax=fmax, xfmt="freq")
                g = self.gate_axis()
                return Frame([ax] + ([g] if g else []), title=self.TITLE + self.gate_title(), readout=self.gate_readout())
            return None
        mk = self.marker_index()
        # markers and measurements read the marker trace unsmoothed (the vbw only shapes what is drawn)
        self.last = self.trace_data(mk)
        self.last_shown = self.trace_shown(mk)
        level = self.last if self.last is not None else raw[-1] # the auto ref level, with the marker trace blank
        btm, top = self.y_range(level) # the unsmoothed peaks must fit
        fmin, fmax = self.source.freq_range()
        n = len(level)
        frame = Frame([Axis(
            xmin=fmin, xmax=fmax, xfmt="freq", ymin=btm, ymax=top, offscale=self.offscale(level, btm, top),
            traces=self.shrink(self.trace_list()),
        )], title=self.TITLE + (self.gate_title() if self.gated else ""), readout=self.rbw_readout(n) + self.avg_readout())
        if self.last_shown is not None:
            self.ref_frame(frame, self.last_shown)
        self.apply_markers(frame)
        if self.gated:
            frame.readout += self.gate_readout()
            g = self.gate_axis()
            if g is not None:
                frame.axes.append(g)
        return frame
