"""Analog demodulation on rpps (rpps.wave.demod): AM, FM, PM and SSB of a carrier, with its measurements"""
import numpy as np

from ..base import About, Plot, plot
from ..frame import BLUE, GREEN, YELLOW, Axis, Frame, Trace
from ..freq import fmt_hz, freq_text, hz
from ..reduce import envelope
from ..settings import Setting

MODES = ("AM", "FM", "PM", "USB", "LSB")
# per mode: the audio's axis format, its unit and its color
LOOK = {"AM": ("num", "%", YELLOW), "FM": ("freq", "Hz", GREEN), "PM": ("num", "rad", BLUE),
        "USB": ("num", "", YELLOW), "LSB": ("num", "", YELLOW)}

@plot("Analog Demod")
class AnalogDemod(Plot):
    """AM, FM, PM, USB or LSB demodulation of a carrier (rpps.wave.demod): the modulation against time and its spectrum,
    with the depth or deviation, the carrier's offset, and the modulating tone and SINAD when one tone carries it"""
    TITLE = "Analog Demod"
    CATEGORY = "Analog demodulation"
    ABOUT = About(
        data='The block shifted to the carrier (the strongest, or the one given), filtered to the demod bandwidth and '
             'demodulated by rpps: its envelope (AM), frequency (FM), unwrapped phase (PM) or one sideband (USB, LSB)',
        shows='The demodulated signal against time and its spectrum; depth or deviation, the carrier offset, and the '
              'modulating tone and SINAD when one tone holds most of it',
        use=('Measure FM deviation, PM phase deviation or AM depth', "Check a modulating tone's frequency and distortion (SINAD)",
             'Listen in on SSB by eye: its audio against time and its spectrum'),
        cost=9, # the whole span demodulated
    )
    SETTINGS = (
        Setting("mode", "Mode", "select", default="FM", options=MODES, reset=True, group="Demod", help="what is demodulated"),
        Setting("carrier", "Carrier", "text", default="", coerce=freq_text, hint="strongest", group="Demod",
                help="the carrier (SSB: the suppressed carrier), blank for the strongest"),
        Setting("demod_bw", "Bandwidth", "text", default="", coerce=freq_text, hint="sample rate", group="Demod",
                help="the channel demodulated (SSB: the sideband's width)"),
        Setting("count", "Samples", "int", default=4096, min=16, step=256, group="Timebase", help="audio samples drawn"),
    )

    def carrier_offset(self, x: np.ndarray, fs: float) -> float:
        """The carrier's offset from the tuning: the one given, else the strongest peak refined to the power centroid
        around it (the strongest bin of FM is a sideband)"""
        if self.carrier:
            return hz(self.carrier, 0) - self.source.cf
        n = len(x)
        P = np.abs(np.fft.fft(x * np.hanning(n)))**2
        f = np.fft.fftfreq(n, 1 / fs)
        k = int(np.argmax(P))
        near = np.abs(f - f[k]) <= (hz(self.demod_bw, 0) / 2 if self.demod_bw else fs / 2)
        return float(np.sum(f[near] * P[near]) / np.sum(P[near]))

    def render(self):
        from rpps.wave import demod
        x = np.asarray(self.source.samples, dtype=np.complex128)
        if len(x) < 64:
            return None
        fs = self.source.fs or 1.0
        off = self.carrier_offset(x, fs)
        y = x * np.exp(-2j * np.pi * off * np.arange(len(x)) / fs)
        bw = min(hz(self.demod_bw, 0) if self.demod_bw else fs, fs)
        mode = self.mode
        # the whole channel's modulation kept as audio (not just voice): what a measurement wants to see
        audio, afs, m = demod(y, fs, mode.lower(), bw=bw, audio_bw=bw / 2 if mode in ("AM", "FM", "PM") else bw)
        d = audio.astype(np.float64) * (100.0 if mode == "AM" else 1.0)
        readout = [("Carrier", fmt_hz(self.source.cf + off))]
        if mode == "AM":
            readout += [("Depth", f"{m.depth * 100:.1f}%"), ("RMS", f"{d.std():.2f}%")]
        elif mode == "FM":
            readout += [("Offset", fmt_hz(m.offset_hz)), ("Deviation", f"{fmt_hz(m.deviation_hz)} pk"),
                        ("RMS", fmt_hz(m.deviation_rms_hz))]
        elif mode == "PM":
            readout += [("Offset", fmt_hz(m.offset_hz)), ("Deviation", f"{m.phase_dev_rad:.3g} rad pk"),
                        ("RMS", f"{m.phase_dev_rms_rad:.3g} rad")]
        else:
            readout.append(("Power", f"{m.power_db:.1f} dB"))
        if m.tone_hz is not None:
            readout += [("Mod freq", fmt_hz(m.tone_hz)), ("SINAD", f"{m.sinad_db:.1f} dB")]
        # the modulation's spectrum
        S = np.abs(np.fft.rfft(d * np.hanning(len(d))))**2
        sf = np.fft.rfftfreq(len(d), 1 / afs)
        S[:3] = 0 # what is left of DC
        sdb = 10 * np.log10(np.maximum(S / max(float(S.max()), 1e-30), 1e-12))
        yfmt, unit, color = LOOK[mode]
        shown = d[-self.count:]
        tt = np.arange(len(shown)) / afs
        tx, ty = envelope(tt, shown)
        lim = float(np.max(np.abs(shown))) * 1.2 or 1.0
        return Frame([
            Axis(xmin=0.0, xmax=len(shown) / afs, xfmt="time", ymin=-lim, ymax=lim, yfmt=yfmt, xlabel="Time",
                 ylabel=f"{mode} ({unit})" if unit else mode, traces=[Trace(ty, tx, color=color, name="demod")]),
            Axis(xmin=0.0, xmax=float(afs / 2), xfmt="freq", ymin=-100.0, ymax=5.0, ylabel="dB",
                 traces=[Trace(sdb, sf, color=color, name="spectrum")]),
        ], title=self.TITLE, readout=readout)
