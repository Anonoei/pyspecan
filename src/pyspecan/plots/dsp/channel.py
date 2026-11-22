"""Channel and signal analysis: the selected link's response (network analyzer), impulse response, and the signal's
cyclostationary features (cyclic spectrum)"""
import numpy as np

from ..base import About, plot
from ..frame import (
    BLUE,
    GREEN,
    IMAGE,
    LINE,
    RED,
    YELLOW,
    Axis,
    Frame,
    Image,
    Marker,
    Trace,
    fmt_time,
    time_unit,
)
from ..freq import SETTING_CMAP, fmt_hz
from ..settings import Setting
from .analyzer import analyzer
from .common import SETTING_DECAY, DSPPlot, ResponseMixin


@plot("Network Analyzer")
class NetworkAnalyzer(ResponseMixin, DSPPlot):
    """The selected link's frequency response: magnitude, phase and group delay across the signal, from its ideal
    waveform (the decided symbols through the ideal pulse) to what was received. Measured blind, on live traffic,
    the way a vector signal analyzer reads the channel from its equalizer: no stimulus is needed, so it shows the
    whole path (transmitter filters, the air, this receiver) and not one device on its own"""
    TITLE = "Network Analyzer"
    CATEGORY = "Channel and signal analysis"
    ABOUT = About(
        data='The analysed signal (the Analysis settings, or a box clicked on the signals marker) shifted'
             ' to 0 Hz, filtered and decimated; its symbol rate, roll-off, timing and carrier recovered '
             '(rpps); the received waveform over the ideal one, their cross spectra averaged',
        shows="Magnitude, phase deviation and group delay of the link across the signal's band",
        use=(
            "Measure a channel's or filter's response on live traffic, no stimulus",
            'Find ripple, tilt and group delay distortion',
        ),
        cost=19,
    )
    FEATURES = frozenset({LINE})
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("resolution", "Points / symbol rate", "int", default=16, min=4, max=128, group="Display",
                help="frequency resolution, points across one symbol rate"),
        SETTING_DECAY.with_(default=0.8),
    )

    def reset(self):
        super().reset()
        self.changed_lock()

    def render(self):
        sel, lk, why = self.analyse()
        if lk is None:
            return self.empty([Axis(ylabel="Magnitude (dB)"), Axis(ylabel="Phase (deg)"), Axis(ylabel="Group delay")], sel, why)
        f, band = self.accumulate(lk)
        edge = (1 + lk.beta) * lk.baud / 2
        if band.sum() < 4:
            return self.empty([Axis(ylabel="Magnitude (dB)"), Axis(ylabel="Phase (deg)"), Axis(ylabel="Group delay")], sel, "too narrow")
        H = self.sxr[band] / self.srr[band]
        fb = f[band]
        mid = np.abs(fb) <= lk.baud / 4
        mag = 20 * np.log10(np.abs(H) + 1e-30)
        mag -= np.mean(mag[mid]) if mid.any() else np.mean(mag)
        ph = np.unwrap(np.angle(H))
        slope, icept = np.polyfit(fb, ph, 1) # a pure delay (and the phase) are not the channel's shape
        ph_dev = np.degrees(ph - (slope * fb + icept))
        gd = -np.diff(ph) / (2 * np.pi * np.diff(fb))
        gd_x = (fb[1:] + fb[:-1]) / 2
        gd_dev = gd - np.median(gd)
        scale, unit = time_unit(max(float(np.max(np.abs(gd_dev))), 1e-12) * 4)
        x0 = sel.freq # type: ignore
        xmin, xmax = x0 - edge, x0 + edge
        def rng(v, least):
            a = max(least, float(np.max(np.abs(v))) * 1.2)
            return -a, a
        mlo, mhi = rng(mag, 3.0)
        plo, phi = rng(ph_dev, 10.0)
        glo, ghi = rng(gd_dev / scale, 1.0)
        axes = [
            Axis(xmin=xmin, xmax=xmax, xfmt="freq", ymin=mlo, ymax=mhi, ylabel="Magnitude (dB)",
                 traces=[Trace(mag, x0 + fb, color=YELLOW, name="mag")]),
            Axis(xmin=xmin, xmax=xmax, xfmt="freq", ymin=plo, ymax=phi, ylabel="Phase (deg)",
                 traces=[Trace(ph_dev, x0 + fb, color=BLUE, name="phase")]),
            Axis(xmin=xmin, xmax=xmax, xfmt="freq", ymin=glo, ymax=ghi, ylabel=f"Group delay ({unit})",
                 traces=[Trace(gd_dev / scale, x0 + gd_x, color=GREEN, name="gd")]),
        ]
        delay = -slope / (2 * np.pi) # s, the linear phase taken out
        return Frame(axes, title=self.TITLE, readout=[
            *self.sel_readout(sel), ("Mod", lk.mod), ("Baud", fmt_hz(lk.baud).replace("Hz", "Bd")),
            ("Ripple", f"{np.ptp(mag):.2f} dB p-p"), ("Phase", f"{np.std(ph_dev):.2f}° rms"),
            ("GD", f"{np.ptp(gd_dev) / scale:.3g} {unit} p-p"), ("Delay", fmt_time(delay)),
            ("Es/N0", f"{lk.esn0:.1f} dB"),
        ])


@plot("Impulse Response")
class ImpulseResponse(ResponseMixin, DSPPlot):
    """The link's impulse response: the network analyzer's frequency response, tapered (a hard band edge rings at
    -13 dB) and inverse transformed. The main path is at 0, each echo shows by its delay and level. A band limited
    signal can not show delays much finer than one over its bandwidth (the resolution in the readout): closer echoes
    widen the main path instead of standing apart"""
    TITLE = "Impulse Response"
    CATEGORY = "Channel and signal analysis"
    ABOUT = About(
        data='The analysed signal (the Analysis settings, or a box clicked on the signals marker) shifted'
             ' to 0 Hz, filtered and decimated; its symbol rate, roll-off, timing and carrier recovered '
             "(rpps); the link's frequency response, tapered and inverse transformed",
        shows="The link's impulse response: the main path at 0, each echo by its delay and level",
        use=('Find multipath echoes and their delays', "Check a cable's or antenna's reflections"),
        cost=19,
    )
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("resolution", "Points / symbol rate", "int", default=32, min=4, max=256, group="Display",
                help="frequency points per symbol rate: the delays shown span that many symbols"),
        Setting("taper", "Taper", "select", default="hann", options=("hann", "blackman"), group="Display",
                help="hann: finer delays, sidelobes at -31 dB. blackman: wider, sidelobes under -58 dB (weaker echoes show)"),
        SETTING_DECAY.with_(default=0.8),
    )
    TAPERS: dict = {"hann": (np.hanning, 2.0, -28.0), "blackman": (np.blackman, 3.0, -45.0)} # window, width (1/BW), echo floor

    def reset(self):
        super().reset()
        self.changed_lock()

    def render(self):
        sel, lk, why = self.analyse()
        if lk is None:
            return self.empty([Axis(xfmt="time", ylabel="dB")], sel, why)
        win, width, floor = self.TAPERS[self.taper] # type: ignore
        f, band = self.accumulate(lk)
        nfft = len(f)
        idx = np.flatnonzero(band)
        H = np.zeros(nfft, complex)
        H[idx] = self.sxr[idx] / self.srr[idx] * win(len(idx) + 2)[1:-1] # type: ignore
        h = np.fft.fftshift(np.fft.ifft(np.fft.ifftshift(H)))
        main = int(np.argmax(np.abs(h)))
        h = np.roll(h, nfft // 2 - main) # the main path at 0
        db = 20 * np.log10(np.abs(h) / max(float(np.abs(h).max()), 1e-30) + 1e-12)
        t = (np.arange(nfft) - nfft // 2) / lk.Fs
        res = width / max(float(f[idx[-1]] - f[idx[0]]), 1.0) # the tapered main path's half width
        readout = [*self.sel_readout(sel), ("Mod", lk.mod), ("Resolution", fmt_time(res))]
        from ...measure import peaks
        echoes = [int(j) for j in peaks.find_peaks(db, 8, floor, 1.0) if abs(t[j]) >= res] # over the taper's sidelobes
        for j in echoes[:3]:
            readout.append(("Echo", f"{db[j]:.1f} dB at {fmt_time(t[j])}"))
        if not echoes:
            readout.append(("Echoes", f"none over {floor:g} dB"))
        return Frame([Axis(
            xmin=float(t[0]), xmax=float(t[-1]), xfmt="time", ymin=-60.0, ymax=5.0, xlabel="Delay", ylabel="dB",
            traces=[Trace(db, t, color=YELLOW, name="h")],
        )], title=self.TITLE, readout=readout)


@plot("Cyclic Spectrum")
class CyclicSpectrum(DSPPlot):
    """Cyclostationary features of the selected signal, no lock needed: the spectral correlation's peak at each cycle
    frequency (the symbol rate and its multiples stand out for a linear modulation), the spectral coherence over
    frequency and cycle frequency, and what rpps reads from them (rate, carrier symmetry, offset, envelope)"""
    TITLE = "Cyclic Spectrum"
    CATEGORY = "Channel and signal analysis"
    ABOUT = About(
        data='The analysed signal at baseband (no lock needed): its spectral correlation and coherence '
             'over cycle frequencies (rpps)',
        shows='The correlation against cycle frequency (symbol rate lines marked) and the coherence '
              'image; the rate, carrier symmetry and envelope found blind',
        use=(
            "Find an unknown signal's symbol rate",
            'Tell modulation families apart by their carrier lines (x^2, x^4, x^8)',
            'Detect a signal under noise or another signal',
        ),
        cost=30,
    )
    FEATURES = frozenset({LINE, IMAGE})
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("channels", "Channels", "int", default=64, min=16, max=512, step=16, group="Processing", advanced=True,
                help="frequency channels (resolution fs / channels)"),
        Setting("samples", "Samples", "int", default=4096, min=512, max=65536, step=512, group="Processing",
                help="baseband samples used (cycle frequency resolution)"),
        SETTING_DECAY, SETTING_CMAP.with_(default="radar"),
    )

    def reset(self):
        super().reset()
        self.changed_lock()

    def changed_lock(self):
        self.prof = self.coh = None

    def render(self):
        from rpps.analysis.spectrum.cyclic import alpha_profile, features
        from rpps.analysis.spectrum.scf import coherence
        if not len(self.source.samples):
            return None
        an = analyzer(self.source)
        sel = an.selection(self.dsp_freq, self.dsp_bw) # type: ignore
        if sel is None:
            return self.empty([Axis(xfmt="freq", ylabel="|SCF|")], None, "no signal found")
        x, Fs = an.baseband(sel)
        x = x[-self.samples:] # type: ignore
        if len(x) < 4 * self.channels: # type: ignore
            return self.empty([Axis(xfmt="freq", ylabel="|SCF|")], sel, "too few samples")
        key = (sel.key, Fs)
        if key != self.sel_key:
            self.sel_key = key
            self.changed_lock()
        nch = self.channels # type: ignore
        a, prof = alpha_profile(x, Fs, nch)
        prof = prof / max(float(prof.max()), 1e-30)
        ff, aa, cc = coherence(x, Fs, nch)
        rows, cols = 96, 192
        grid = np.zeros((rows, cols))
        i = np.clip(((ff / Fs + 0.5) * rows).astype(int), 0, rows - 1)
        j = np.clip(((aa / Fs + 1) / 2 * cols).astype(int), 0, cols - 1)
        np.maximum.at(grid, (i, j), cc)
        grid[:, np.abs((np.arange(cols) + 0.5) / cols * 2 - 1) * Fs <= Fs / nch] = 0 # alpha = 0 is the power spectrum
        if self.prof is None or len(self.prof) != len(prof):
            self.prof, self.coh = prof, grid
        else:
            self.prof = self.prof * self.decay + prof * (1 - self.decay) # type: ignore
            self.coh = np.maximum(self.coh * self.decay, grid) # type: ignore
        readout = [*self.sel_readout(sel)]
        marks = []
        try:
            feat = features(x, Fs)
        except (ValueError, IndexError, FloatingPointError) as e:
            feat = None
            readout.append(("Features", str(e)))
        if feat is not None:
            if feat.baud is not None:
                readout.append(("Baud", f"{fmt_hz(feat.baud).replace('Hz', 'Bd')} ({feat.baud_from}, {feat.baud_line.db:.1f} dB)"))
                for m in (-1, 1):
                    marks.append(Marker(m * feat.baud, 0.0, "baud" if m > 0 else "", RED, kind="vline"))
            else:
                readout.append(("Baud", "no rate line"))
            if feat.order is not None:
                from rpps.analysis.spectrum.cyclic import ORDER_NAMES
                readout.append(("Carrier", f"x^{feat.order} line, {ORDER_NAMES.get(feat.order, '')}, CFO {fmt_hz(feat.cfo)}"))
            readout.append(("Envelope", f"{feat.envelope:.2f} (1 constant, 2 Gaussian)"))
        img = np.rint(self.coh / max(float(self.coh.max()), 1e-12) * 255).astype(np.uint8)[::-1] # type: ignore
        return Frame([
            Axis(xmin=float(-Fs), xmax=float(Fs), xfmt="freq", ymin=0.0, ymax=1.05, xlabel="Cycle frequency", ylabel="|SCF| (rel)",
                 traces=[Trace(self.prof, a, color=YELLOW, name="profile")], markers=marks),
            Axis(xmin=float(-Fs), xmax=float(Fs), xfmt="freq", ymin=float(-Fs / 2), ymax=float(Fs / 2), yfmt="freq",
                 xlabel="Cycle frequency", ylabel="Frequency", image=Image(img, cmap=self.cmap)),
        ], title=self.TITLE, readout=readout)
