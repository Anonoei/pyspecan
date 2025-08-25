import matplotlib.pyplot as plt

from ..plot import Plot

class PSD(Plot):
    __slots__ = ("Fs", "cf", "vbw_hz")
    def __init__(self, ax, Fs=1.0, cf=0.0, vbw_hz=None):
        super().__init__(ax)
        self.Fs = Fs
        self.cf = cf
        self.vbw_hz = vbw_hz

def psd(ax, samps, Fs=1.0, cf=0.0, vbw_hz=None):
    if ax is None:
        fig, ax = plt.subplots()
    x = freq_axis(len(samps), Fs, cf)
    y = utils.psd(samps, Fs, vbw_hz)

    if isinstance(ax, mpl.lines.Line2D):
        ax.set_data(x, y)
        line = ax
    else:
        line, = ax.plot(x, y, c="y")
        ax.grid(True)
        ax.set_title("PSD")
        ax.set_title("Freq Domain", loc="left")
        ax.set_title(f"{len(samps)} samples", loc="right")
        ax.set_xlabel("Frequency [Hz]")
        ax.set_ylabel("Magnitude [dB]")
        ax.set_xlim(x[0], x[-1])
    return line
