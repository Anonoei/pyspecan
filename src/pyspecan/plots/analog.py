"""Analog measurements: phase noise of a carrier, and AM / FM / PM demodulation"""
import numpy as np

from ..measure import units
from ..measure.windows import WindowLUT
from .base import About, Plot, plot
from .frame import BLUE, GREEN, YELLOW, Axis, Frame, Trace
from .freq import fmt_hz, freq_text, hz, to_psd
from .reduce import envelope
from .settings import Setting


def _db(v: float) -> float:
    return float(10 * np.log10(max(v, 1e-30)))

@plot("Phase Noise")
class PhaseNoise(Plot):
    """Single sideband phase noise L(f) of a carrier in dBc/Hz against the offset from it, on a log axis, with the
    integrated phase noise (rms degrees) and jitter. The spectrum method: the noise density at each offset over the
    carrier's power, so the analyzer's own noise and its window's skirt set the floor, and the resolution (the FFT size)
    the closest offset"""
    TITLE = "Phase Noise"
    CATEGORY = "Measurements"
    ABOUT = About(
        data="Large FFTs (spanning blocks) averaged; the carrier's power from its main lobe; the noise "
             'density at each offset over it',
        shows='L(f) in dBc/Hz against the offset from the carrier on a log axis; the integrated phase '
              'noise and jitter',
        use=('Characterize an oscillator or synthesizer', 'Compare reference sources'),
        cost=1.4,
    )
    SETTINGS = (
        Setting("window", "Window", "select", default="blackman", options=tuple(WindowLUT), reset=True, group="Processing",
                help="FFT window, a narrow main lobe reaches closer offsets"),
        Setting("pn_nfft", "FFT size", "int", default=0, min=0, max=1 << 20, step=1024, hint="0 = analyzer's", reset=True,
                group="Processing", help="larger reaches closer offsets (frames span blocks)"),
        Setting("avg_count", "Averages", "int", default=20, min=1, max=10000, reset=True, group="Processing",
                help="frames averaged (running average)"),
        Setting("carrier", "Carrier", "text", default="", coerce=freq_text, hint="strongest", group="Measurement",
                help="the carrier's frequency, blank for the strongest"),
        Setting("sideband", "Sideband", "select", default="upper", options=("upper", "lower", "both"), group="Measurement",
                help="offsets above, below, or the mean of both"),
        Setting("int_lo", "Integrate from", "text", default="", coerce=freq_text, hint="closest", group="Measurement",
                help="lowest offset integrated"),
        Setting("int_hi", "Integrate to", "text", default="", coerce=freq_text, hint="farthest", group="Measurement",
                help="highest offset integrated"),
        Setting("smooth", "Points", "int", default=200, min=0, max=5000, group="Display",
                help="log spaced points drawn (each the mean of its bins), 0 for every bin"),
    )

    LOBE = 4 # bins either side of the carrier that are its main lobe (its power), not noise

    def reset(self):
        self.avg = None
        self.count = 0

    def render(self):
        src = self.source
        nfft = self.pn_nfft or src.nfft
        spectra = src.spectra("rt", self.window, nfft)
        if len(spectra):
            lin = units.db_to_lin(to_psd(spectra, src.fs, self.window, "dB/Hz")).mean(axis=0) # power per Hz
            if self.avg is None or len(self.avg) != nfft:
                self.avg, self.count = lin, 0
            self.count = min(self.count + len(spectra), self.avg_count)
            a = len(spectra) / self.count
            self.avg = self.avg * (1 - min(a, 1)) + lin * min(a, 1)
        if self.avg is None:
            return None
        df = src.fs / nfft
        freqs = src.freq_range()[0] + np.arange(nfft) * df
        k = int(np.argmin(np.abs(freqs - hz(self.carrier, 0)))) if self.carrier else int(np.argmax(self.avg))
        L = self.LOBE
        pc = float(np.sum(self.avg[max(0, k - L):k + L + 1]) * df) # the carrier's power: its main lobe
        up = self.avg[k + L + 1:]
        down = self.avg[:max(0, k - L)][::-1]
        if self.sideband == "upper":
            side = up
        elif self.sideband == "lower":
            side = down
        else:
            m = min(len(up), len(down))
            side = (up[:m] + down[:m]) / 2
        title = self.TITLE
        if len(side) < 4:
            return Frame([Axis(xlog=True, xfmt="freq", ylabel="dBc/Hz")], title=title,
                         readout=[("Carrier", fmt_hz(freqs[k])), ("Offsets", "none on this side")])
        off = (np.arange(len(side)) + L + 1) * df
        rel = side / pc # dBc/Hz, linear
        x, y = off, rel
        if self.smooth and len(off) > self.smooth:
            edges = np.geomspace(off[0], off[-1] * (1 + 1e-9), self.smooth + 1)
            j = np.digitize(off, edges) - 1
            cnt = np.bincount(j, minlength=self.smooth)
            keep = cnt > 0
            x = (np.bincount(j, off, self.smooth) / np.maximum(cnt, 1))[keep]
            y = (np.bincount(j, rel, self.smooth) / np.maximum(cnt, 1))[keep]
        ydb = 10 * np.log10(np.maximum(y, 1e-30))
        lo = hz(self.int_lo, off[0]) if self.int_lo else off[0]
        hi = hz(self.int_hi, off[-1]) if self.int_hi else off[-1]
        band = (off >= lo) & (off <= hi)
        var = 2 * float(np.sum(rel[band]) * df) # rad^2: both sidebands of the single sideband density
        rms = np.sqrt(var)
        fc = freqs[k] # absolute
        readout = [("Carrier", f"{fmt_hz(fc)}, {_db(pc):.1f} dBFS"), ("RBW", fmt_hz(df * 1.5))]
        for o in (1e2, 1e3, 1e4, 1e5, 1e6):
            if off[0] <= o <= off[-1]:
                readout.append((f"L({fmt_hz(o).replace(' ', '')})", f"{10 * np.log10(np.interp(o, off, rel)):.1f} dBc/Hz"))
        readout.append(("Integrated", f"{np.degrees(rms):.3g}° rms ({fmt_hz(lo)} to {fmt_hz(hi)})"))
        if fc > 0:
            readout.append(("Jitter", f"{rms / (2 * np.pi * fc) * 1e12:.3g} ps rms"))
        top, btm = float(np.ceil(ydb.max() / 10) * 10 + 10), float(np.floor(ydb.min() / 10) * 10 - 10)
        return Frame([Axis(
            xmin=float(off[0]), xmax=float(off[-1]), xlog=True, xfmt="freq", ymin=btm, ymax=top,
            xlabel="Offset", ylabel="dBc/Hz", traces=[Trace(ydb, x, color=YELLOW, name="pn")],
        )], title=title, readout=readout)

MODES = ("AM", "FM", "PM")

@plot("Analog Demod")
class AnalogDemod(Plot):
    """AM, FM or PM demodulation of a carrier: the modulation against time and its spectrum, with the depth or
    deviation, the modulating frequency and the SINAD"""
    TITLE = "Analog Demod"
    CATEGORY = "Analog demodulation"
    ABOUT = About(
        data='The block shifted to the carrier, filtered to the demod bandwidth, then its envelope (AM), '
             'phase step (FM) or unwrapped phase (PM)',
        shows='The demodulated signal against time and its spectrum; depth or deviation, the modulating '
              'frequency, SINAD',
        use=('Measure FM deviation or AM depth', "Check a modulating tone's frequency and distortion (SINAD)"),
        cost=5.7,
    )
    SETTINGS = (
        Setting("mode", "Mode", "select", default="FM", options=MODES, reset=True, group="Demod", help="what is demodulated"),
        Setting("carrier", "Carrier", "text", default="", coerce=freq_text, hint="strongest", group="Demod",
                help="the carrier, blank for the strongest"),
        Setting("demod_bw", "Bandwidth", "text", default="", coerce=freq_text, hint="sample rate", group="Demod",
                help="filter around the carrier before demodulating"),
        Setting("count", "Samples", "int", default=4096, min=16, step=256, group="Timebase", help="samples drawn"),
    )

    def render(self):
        x = np.asarray(self.source.samples, dtype=np.complex128)
        if len(x) < 64:
            return None
        fs = self.source.fs or 1.0
        n = len(x)
        X = np.fft.fft(x * np.hanning(n))
        f = np.fft.fftfreq(n, 1 / fs)
        if self.carrier:
            off = hz(self.carrier, 0) - self.source.cf
        else: # the strongest peak, refined to the power centroid around it (the strongest bin of FM is a sideband)
            P = np.abs(X)**2
            k = int(np.argmax(P))
            near = np.abs(f - f[k]) <= (hz(self.demod_bw, 0) / 2 if self.demod_bw else fs / 2)
            off = float(np.sum(f[near] * P[near]) / np.sum(P[near]))
        y = x * np.exp(-2j * np.pi * off * np.arange(n) / fs)
        bw = hz(self.demod_bw, 0) if self.demod_bw else 0.0
        if 0 < bw < fs:
            Y = np.fft.fft(y)
            Y[np.abs(f) > bw / 2] = 0
            y = np.fft.ifft(Y)
        mode = self.mode
        readout = [("Carrier", fmt_hz(self.source.cf + off))]
        if mode == "AM":
            env = np.abs(y)
            mean = float(env.mean()) or 1.0
            d = (env / mean - 1) * 100
            yfmt, unit, color = "num", "%", YELLOW
            readout += [("Depth", f"+{d.max():.1f}% / {d.min():.1f}%"), ("RMS", f"{d.std():.2f}%")]
        elif mode == "FM":
            d = np.angle(y[1:] * np.conj(y[:-1])) * fs / (2 * np.pi)
            readout.append(("Offset", fmt_hz(float(d.mean()))))
            d = d - d.mean()
            yfmt, unit, color = "freq", "Hz", GREEN
            readout += [("Deviation", f"{fmt_hz(float(np.max(np.abs(d))))} pk"), ("RMS", fmt_hz(float(d.std())))]
        else:
            ph = np.unwrap(np.angle(y))
            t = np.arange(len(ph))
            d = ph - np.polyval(np.polyfit(t, ph, 1), t) # a carrier offset is a phase ramp
            yfmt, unit, color = "num", "rad", BLUE
            readout += [("Deviation", f"{np.max(np.abs(d)):.3g} rad pk"), ("RMS", f"{d.std():.3g} rad")]
        # the modulation's spectrum: its strongest tone is the modulating frequency
        S = np.abs(np.fft.rfft(d * np.hanning(len(d))))**2
        sf = np.fft.rfftfreq(len(d), 1 / fs)
        S[:3] = 0 # what is left of DC
        top = int(np.argmax(S))
        if S[top] > 0 and float(np.std(d)) > 1e-6 * (100 if mode == "AM" else 1): # there is modulation
            tone = float(np.sum(S[max(0, top - 3):top + 4]))
            rest = float(np.sum(S)) - tone
            readout += [("Mod freq", fmt_hz(float(sf[top]))), ("SINAD", f"{_db(float(np.sum(S)) / max(rest, 1e-30)):.1f} dB")]
        sdb = 10 * np.log10(np.maximum(S / max(float(S.max()), 1e-30), 1e-12))
        fmax = min(fs / 2, bw / 2) if bw else fs / 2
        keep = sf <= fmax
        shown = d[-self.count:]
        tt = np.arange(len(shown)) / fs
        tx, ty = envelope(tt, shown)
        lim = float(np.max(np.abs(shown))) * 1.2 or 1.0
        return Frame([
            Axis(xmin=0.0, xmax=len(shown) / fs, xfmt="time", ymin=-lim, ymax=lim, yfmt=yfmt, xlabel="Time",
                 ylabel=f"{mode} ({unit})", traces=[Trace(ty, tx, color=color, name="demod")]),
            Axis(xmin=0.0, xmax=float(fmax), xfmt="freq", ymin=-100.0, ymax=5.0, ylabel="dB",
                 traces=[Trace(sdb[keep], sf[keep], color=color, name="spectrum")]),
        ], title=self.TITLE, readout=readout)
