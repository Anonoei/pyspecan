"""Analog measurements: phase noise of a carrier (AM / FM / PM / SSB demodulation is in plots.dsp.analog, on rpps)"""
import numpy as np

from ..measure import units
from ..measure.windows import WindowLUT
from .base import About, Plot, plot
from .frame import YELLOW, Axis, Frame, Trace
from .freq import fmt_hz, freq_text, hz, to_psd
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
