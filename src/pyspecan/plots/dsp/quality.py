"""Modulation quality: the selected signal's error vector per symbol and its spectrum"""
import numpy as np

from ..base import About, plot
from ..frame import (
    BLUE,
    GREEN,
    YELLOW,
    Axis,
    Frame,
    Trace,
)
from ..settings import Setting
from .common import SETTING_DECAY, DSPPlot, error_summary, errors, pair, welch


@plot("Error Vector")
class ErrorVector(DSPPlot):
    """Per symbol: the error vector magnitude, the magnitude error and the phase error against the decided points"""
    TITLE = "Error Vector"
    CATEGORY = "Modulation quality"
    ABOUT = About(
        data='The analysed signal (the Analysis settings, or a box clicked on the signals marker) shifted'
             ' to 0 Hz, filtered and decimated; its symbol rate, roll-off, timing and carrier recovered '
             "(rpps); each symbol's error against its decided point",
        shows='EVM, magnitude error and phase error per symbol, with the error summary (peak EVM, MER, IQ'
              ' offset, gain imbalance, quadrature error)',
        use=(
            'Find the symbols with large errors (bursts of interference)',
            'Tell amplitude problems from phase problems',
        ),
        cost=6,
    )
    SETTINGS = DSPPlot.SETTINGS + (
        Setting("count", "Symbols", "int", default=500, min=16, max=20000, step=100, group="Display", help="latest symbols shown"),
    )

    def render(self):
        sel, lk, why = self.analyse()
        if lk is None:
            return self.empty([Axis(ylabel="EVM (%)"), Axis(ylabel="Mag err (%)"), Axis(ylabel="Phase err (deg)")], sel, why)
        _, evm, mag, ph = errors(lk)
        n = min(self.count, len(evm))
        k = np.arange(n, dtype=float) # counted from the first one shown
        def sym(v, least):
            a = max(least, float(np.max(np.abs(v))) * 1.2)
            return -a, a
        mlo, mhi = sym(mag[-n:], 5.0)
        plo, phi = sym(ph[-n:], 5.0)
        x0, x1 = float(k[0]), float(k[-1])
        return Frame([
            Axis(xmin=x0, xmax=x1, ymin=0.0, ymax=max(5.0, float(evm[-n:].max()) * 1.2), ylabel="EVM (%)",
                 traces=[Trace(evm[-n:], k, color=YELLOW, name="evm")]),
            Axis(xmin=x0, xmax=x1, ymin=mlo, ymax=mhi, ylabel="Mag err (%)", traces=[Trace(mag[-n:], k, color=GREEN, name="mag")]),
            Axis(xmin=x0, xmax=x1, ymin=plo, ymax=phi, ylabel="Phase err (deg)", xlabel="Symbol",
                 traces=[Trace(ph[-n:], k, color=BLUE, name="phase")]),
        ], title=self.TITLE, readout=[*self.sel_readout(sel), ("Mod", lk.mod), ("EVM", f"{lk.evm:.2f}% rms"), *error_summary(lk)])


@plot("Error Vector Spectrum")
class ErrorVectorSpectrum(DSPPlot):
    """The spectrum of the error waveform (what was received minus the ideal waveform of the decided symbols) over
    the signal's: where in the band the errors are, an interferer or a filter's edge shows up here"""
    TITLE = "Error Vector Spectrum"
    CATEGORY = "Modulation quality"
    ABOUT = About(
        data='The analysed signal (the Analysis settings, or a box clicked on the signals marker) shifted'
             ' to 0 Hz, filtered and decimated; its symbol rate, roll-off, timing and carrier recovered '
             '(rpps); the received waveform minus the ideal one (the decided symbols through the ideal '
             'pulse), its spectrum averaged',
        shows="The error's spectrum under the signal's, and the error to signal ratio in band",
        use=('Find interference or spurs hidden under the signal', 'See filter edges or a tilt causing errors'),
        cost=10,
    )
    SETTINGS = DSPPlot.SETTINGS + (SETTING_DECAY.with_(default=0.7),)

    def reset(self):
        super().reset()
        self.changed_lock()

    def changed_lock(self):
        self.se = self.ss = None

    def render(self):
        sel, lk, why = self.analyse()
        if lk is None:
            return self.empty([Axis(xfmt="freq", ylabel="dB")], sel, why)
        nfft = int(2 ** np.ceil(np.log2(max(64, 16 * lk.sps))))
        xr, r = pair(lk)
        g = np.vdot(r, xr) / max(np.vdot(r, r).real, 1e-30) # the received waveform's gain and phase on the ideal
        se, ss = welch(xr - g * r, nfft), welch(xr, nfft)
        if self.se is None or len(self.se) != nfft:
            self.se, self.ss = se, ss
        else:
            self.se, self.ss = self.se * self.decay + se, self.ss * self.decay + ss
        ref = float(self.ss.max()) or 1.0
        f = sel.freq + (np.arange(nfft) - nfft // 2) * (lk.Fs / nfft) # type: ignore
        sdb, edb = 10 * np.log10(self.ss / ref + 1e-30), 10 * np.log10(self.se / ref + 1e-30)
        inband = np.abs(f - sel.freq) <= lk.baud / 2 # type: ignore
        ratio = 10 * np.log10(np.sum(self.se[inband]) / max(np.sum(self.ss[inband]), 1e-30))
        return Frame([Axis(
            xmin=float(f[0]), xmax=float(f[-1]), xfmt="freq", ymin=max(-100.0, float(edb.min()) - 10), ymax=5.0, ylabel="dB",
            traces=[Trace(sdb, f, color=BLUE, alpha=0.5, width=1.0, name="signal"), Trace(edb, f, color=YELLOW, name="error")],
        )], title=self.TITLE, readout=[*self.sel_readout(sel), ("Mod", lk.mod), ("Error / signal", f"{ratio:.1f} dB in band"),
                                       ("EVM", f"{lk.evm:.2f}%")])
