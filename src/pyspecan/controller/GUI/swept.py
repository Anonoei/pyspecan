import numpy as np

from .base import GUIFreqPlot

from .base import FreqPlotController

from ...utils import vbw

class ControllerSwept(FreqPlotController):
    __slots__ = (
        "psd_min", "psd_max",
        "max_count", "psds"
    )
    def __init__(self, view):
        super().__init__(view, 10.0, 10.0, 0.0)
        self.view: GUIFreqPlot = self.view # type: ignore
        # PSD
        # self.view.plotter.ax(0)
        self.psd_min = None
        self.psd_max = None
        self.__init_psd()
        self.view.plotter.ax(0).set_autoscale_on(False)
        self.view.plotter.ax(0).locator_params(axis="x", nbins=5)
        self.view.plotter.ax(0).locator_params(axis="y", nbins=10)
        self.view.plotter.ax(0).grid(True, alpha=0.2)
        # Spectrogram
        # self.view.fig.subplots_adjust(hspace=1.0)
        self.max_count = 100
        self.psds = np.zeros((self.max_count, 1024))
        self.psds[:,:] = -np.inf
        self.__init_spectrogram()
        # self.view.plotter.ax(1).set_autoscale_on(False)
        self.view.plotter.ax(1).locator_params(axis="x", nbins=5)
        self.view.plotter.ax(1).locator_params(axis="y", nbins=10)

        self.set_y()
        self.view.plotter.canvas.draw()

    def reset(self):
        self.psd_min = None
        self.psd_max = None
        self.psds = np.zeros((self.max_count, 1024))
        self.psds[:,:] = -np.inf

    def update(self):
        self.view.plotter.update()

    def set_y(self):
        self.view.plotter.set_ylim(0, self.y_btm, self.y_top)
        self.view.plotter.set_ylim(1, self.max_count, 0)

    def set_scale(self, *args, **kwargs):
        prev = float(self.scale)
        super().set_scale(*args, **kwargs)
        if not prev == self.scale:
            self.set_y()

    def set_ref_level(self, *args, **kwargs):
        prev = float(self.ref_level)
        super().set_ref_level(*args, **kwargs)
        if not prev == self.ref_level:
            self.set_y()

    def set_vbw(self, *args, **kwargs):
        prev = float(self.vbw)
        super().set_vbw(*args, **kwargs)
        if not prev == self.vbw:
            self.psd_min = None
            self.psd_max = None

    def toggle_psd_min(self):
        if self.view.settings["show_max"].get() == 0:
            self.psd_max = None
        self.update()

    def toggle_psd_max(self):
        if self.view.settings["show_min"].get() == 0:
            self.psd_min = None
        self.update()

    def plot(self, freq, psd):
        psd = vbw.vbw(psd, self.vbw)
        self._plot_psd(freq, psd)
        self._plot_spectrogram(freq, psd)

        if np.all(psd < self.y_btm):
            self.view.lbl_lo.place(relx=0.2, rely=0.9, width=20, height=20)
        else:
            if self.view.lbl_lo.winfo_ismapped():
                self.view.lbl_lo.place_forget()
        if np.all(psd > self.y_top):
            self.view.lbl_hi.place(relx=0.2, rely=0.1, width=20, height=20)
        else:
            if self.view.lbl_hi.winfo_ismapped():
                self.view.lbl_hi.place_forget()

    def _plot_psd(self, freq, psd):
        self.view.plotter.ax(0).set_title("PSD")

        if self.view.settings["show_max"].get() == 1:
            if self.psd_max is None:
                self.psd_max = np.repeat(-np.inf, len(psd))
            self.psd_max[psd > self.psd_max] = psd[psd > self.psd_max]
            line_max = self.view.plot(0, freq, self.psd_max, name="psd_max", color="r")
        else:
            line_max = None
        if self.view.settings["show_min"].get() == 1:
            if self.psd_min is None:
                self.psd_min = np.repeat(np.inf, len(psd))
            self.psd_min[psd < self.psd_min] = psd[psd < self.psd_min]
            line_min = self.view.plot(0, freq, self.psd_min, name="psd_min", color="b")
        else:
            line_min = None
        line_psd = self.view.plot(0, freq, psd, name="psd", color="y")

        if not self.view.plotter.ax(0).get_xlim() == (freq[0], freq[-1]):
            self.view.plotter.set_xlim(0, freq[0], freq[-1])
        return (line_psd, line_max, line_min)

    def _plot_spectrogram(self, freq, psd):
        self.view.plotter.ax(1).set_title("Spectrogram")
        self.psds = np.roll(self.psds, 1, axis=0)
        self.psds[0,:] = psd
        # print(self.psds.shape)
        im = self.view.imshow(
            1, self.psds, name="spectrogram",
            vmin=self.y_btm, vmax=self.y_top,
            aspect="auto", origin="upper",
            interpolation="nearest", resample=False, rasterized=True
        )
        return im

    def __init_psd(self):
        self.view.settings["show_min"].set(1)
        self.view.wg_sets["show_min"].configure(command=self.toggle_psd_min)
        self.view.settings["show_max"].set(1)
        self.view.wg_sets["show_max"].configure(command=self.toggle_psd_max)

        self.view.plotter.ax(0).set_autoscale_on(False)
        self.view.plotter.ax(0).locator_params(axis="x", nbins=5)
        self.view.plotter.ax(0).locator_params(axis="y", nbins=10)
        self.view.plotter.ax(0).grid(True, alpha=0.2)

    def __init_spectrogram(self):
        self.view.settings["max_count"].set(str(self.max_count))
