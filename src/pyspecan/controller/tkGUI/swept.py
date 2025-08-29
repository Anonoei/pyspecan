import numpy as np

from .base import GUIFreqPlot

from .base import FreqPlotController

from ...utils import vbw

class ControllerSwept(FreqPlotController):
    """Controller for ViewSwept"""
    __slots__ = (
        "show_psd", "show_spg",
        "psd_min", "psd_max",
        "max_count", "psds"
    )
    def __init__(self, view):
        super().__init__(view, 10.0, 10.0, 0.0)
        self.view: GUIFreqPlot = self.view # type: ignore
        self.show_psd = 1
        self.show_spg = 0
        self.view.settings["show_psd"].set(self.show_psd)
        self.view.wg_sets["show_psd"].configure(command=self.toggle_show_psd)
        self.view.settings["show_spg"].set(self.show_spg)
        self.view.wg_sets["show_spg"].configure(command=self.toggle_show_spg)

        # PSD
        self.psd_min = None
        self.psd_max = None
        self.__init_psd()
        self.view.plotter.ax(0).set_autoscale_on(False)
        self.view.plotter.ax(0).locator_params(axis="x", nbins=5)
        self.view.plotter.ax(0).locator_params(axis="y", nbins=10)
        self.view.plotter.ax(0).grid(True, alpha=0.2)
        # Spectrogram
        self.max_count = 100
        self.psds = np.zeros((self.max_count, 1024))
        self.psds[:,:] = -np.inf
        self.__init_spectrogram()
        # self.view.plotter.ax(1).set_autoscale_on(False)
        self.view.plotter.ax(1).locator_params(axis="x", nbins=5)
        self.view.plotter.ax(1).locator_params(axis="y", nbins=10)

        self.set_y()
        self._toggle_show()
        self.view.plotter.canvas.draw()

    def reset(self):
        self.psd_min = None
        self.psd_max = None
        self.psds = np.zeros((self.max_count, 1024))
        self.psds[:,:] = -np.inf

    def update(self):
        self.view.plotter.update()

    def _toggle_show(self):
        if self.show_psd == 1 and self.show_spg == 1:
            self.view.plotter.ax(0).set_visible(True)
            self.view.plotter.ax(0).set_in_layout(True)
            self.view.plotter.ax(1).set_visible(True)
            self.view.plotter.ax(1).set_in_layout(True)
        elif self.show_psd == 1:
            self.view.plotter.ax(0).set_visible(True)
            self.view.plotter.ax(0).set_position((0.06, 0.05, 0.92, 0.90))
            self.view.plotter.ax(1).set_visible(False)
            self.view.plotter.ax(1).set_position((0,0,0,0))
        elif self.show_spg == 1:
            self.view.plotter.ax(0).set_visible(False)
            self.view.plotter.ax(0).set_position((0,0,0,0))
            self.view.plotter.ax(1).set_visible(True)
            self.view.plotter.ax(1).set_position((0.06, 0.05, 0.92, 0.90))
        # print(f"_toggle_show, psd: {self.show_psd}, spg: {self.show_spg}")
        self.view.plotter.fig.canvas.draw()
        self.view.plotter.fig.canvas.flush_events()

    def toggle_show_psd(self, *args, **kwargs):
        """Toggle PSD plot visibility"""
        self.show_psd = 0 if self.show_psd == 1 else 1
        self.view.settings["show_psd"].set(self.show_psd)
        self._toggle_show()

    def toggle_show_spg(self, *args, **kwargs):
        """Toggle spectrogram plot visibility"""
        self.show_spg = 0 if self.show_spg == 1 else 1
        self.view.settings["show_spg"].set(self.show_spg)
        self._toggle_show()

    def set_y(self):
        """Set plot ylimits"""
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
        """Toggle PSD min-hold visibility"""
        if self.view.settings["show_min"].get() == 0:
            self.psd_max = None
            self.view.plotter.art(0, "psd_min").set_visible(False)
        else:
            self.view.plotter.art(0, "psd_min").set_visible(True)
        self.update()

    def toggle_psd_max(self):
        """Toggle PSD max-hold visibility"""
        if self.view.settings["show_max"].get() == 0:
            self.psd_min = None
            self.view.plotter.art(0, "psd_max").set_visible(False)
        else:
            self.view.plotter.art(0, "psd_max").set_visible(True)
        self.update()

    def plot(self, freq, psd):
        psd = vbw.vbw(psd, self.vbw)
        if self.show_psd:
            self._plot_psd(freq, psd)
        if self.show_spg:
            self._plot_spectrogram(freq, psd)

        self._show_y_location(psd)

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
