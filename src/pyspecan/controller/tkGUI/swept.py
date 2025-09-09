import numpy as np

from ...view.tkGUI.swept import ViewSwept

from .base import FreqPlotController

from ...utils import vbw as _vbw

class ControllerSwept(FreqPlotController):
    """Controller for ViewSwept"""
    __slots__ = (
        "show_psd", "show_spg",
        "psd_min", "psd_max",
        "max_count", "psds"
    )
    def __init__(self, view, ref_level=0.0, scale=10.0, vbw=10.0, window="blackman"):
        super().__init__(view, ref_level, scale, vbw, window)
        self.view: ViewSwept = self.view # type: ignore
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
        self.view.plotter.ax("psd").ax.set_autoscale_on(False)
        # self.view.plotter.ax("psd").ax.locator_params(axis="x", nbins=5)
        self.view.plotter.ax("psd").ax.locator_params(axis="y", nbins=10)
        self.view.plotter.ax("psd").ax.grid(True, alpha=0.2)
        # Spectrogram
        self.max_count = 100
        self.psds = np.zeros((self.max_count, 1024))
        self.psds[:,:] = -np.inf
        self.__init_spectrogram()
        # self.view.plotter.ax("spg").ax.set_autoscale_on(False)
        # self.view.plotter.ax("spg").ax.locator_params(axis="x", nbins=5)
        self.view.plotter.ax("spg").ax.locator_params(axis="y", nbins=5)

        self.set_y()
        self._toggle_show()
        self.update()

    def reset(self):
        self.psd_min = None
        self.psd_max = None
        self.psds = np.zeros((self.max_count, 1024))
        self.psds[:,:] = -np.inf

    def _toggle_show(self):
        if self.show_psd == 1 and self.show_spg == 1:
            self.view.ax("psd").ax.set_visible(True)
            self.view.ax("spg").ax.set_visible(True)
            # self.view.plotter.ax(0).set_in_layout(True)
            # self.view.plotter.ax(1).set_in_layout(True)
            self.view.ax("psd").ax.set_subplotspec(self.view.gs[0])
            self.view.ax("spg").ax.set_subplotspec(self.view.gs[1])
        elif self.show_psd == 1:
            self.view.ax("psd").ax.set_visible(True)
            self.view.ax("spg").ax.set_visible(False)
            self.view.ax("psd").ax.set_subplotspec(self.view.gs[:])
            # self.view.plotter.ax(0).set_position((0.06, 0.05, 0.92, 0.90))
            self.view.ax("spg").ax.set_position((0,0,0,0))
            art = self.view.plotter.ax("spg").art("spg")
            if art is not None:
                art.set_data([[]]) # clear SPG to be safe
        elif self.show_spg == 1:
            self.view.ax("psd").ax.set_visible(False)
            self.view.ax("spg").ax.set_visible(True)
            self.view.ax("psd").ax.set_position((0,0,0,0))
            self.view.ax("spg").ax.set_subplotspec(self.view.gs[:])
            # self.view.plotter.ax(1).set_position((0.06, 0.05, 0.92, 0.90))
        # print(f"_toggle_show, psd: {self.show_psd}, spg: {self.show_spg}")
        self.view.gs.update()
        self.view.fig.canvas.draw()
        self.view.fig.canvas.flush_events()

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

    def update_f(self, f):
        fmin, fmax, fnum = f
        psd_tick = np.linspace(fmin, fmax, 5)
        psd_text = [f"{f:.3f}" for f in psd_tick]
        self.view.ax("psd").set_xlim(fmin, fmax)
        self.view.ax("psd").ax.set_xticks(psd_tick, psd_text)

        spg_tick = np.linspace(0, fnum+1, 5)
        spg_text = psd_text
        self.view.ax("spg").ax.set_xlim(0, fnum)
        self.view.ax("spg").ax.set_xticks(spg_tick, spg_text)

    def set_y(self):
        """Set plot ylimits"""
        self.view.ax("psd").set_ylim(self.y_btm, self.y_top)
        self.view.ax("spg").set_ylim(self.max_count, 0)

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
        art = self.view.ax("psd").art("psd_min")
        if art is None:
            return
        if self.view.settings["show_min"].get() == 0:
            self.psd_max = None
            art.set_visible(False)
        else:
            art.set_visible(True)
        self.update()

    def toggle_psd_max(self):
        """Toggle PSD max-hold visibility"""
        art = self.view.ax("psd").art("psd_max")
        if art is None:
            return
        if self.view.settings["show_max"].get() == 0:
            self.psd_min = None
            art.set_visible(False)
        else:
            art.set_visible(True)
        self.update()

    def plot(self, freq, psd):
        psd = _vbw.vbw(psd, self.vbw)
        if self.show_psd:
            self._plot_psd(freq, psd)
        if self.show_spg:
            self._plot_spectrogram(freq, psd)

        self._show_y_location(psd)
        self.update()

    def _plot_psd(self, freq, psd):
        self.view.ax("psd").ax.set_title("PSD")

        if self.view.settings["show_max"].get() == 1:
            if self.psd_max is None:
                self.psd_max = np.repeat(-np.inf, len(psd))
            self.psd_max[psd > self.psd_max] = psd[psd > self.psd_max]
            line_max = self.view.ax("psd").plot(freq, self.psd_max, name="psd_max", color="r")
        else:
            line_max = None
        if self.view.settings["show_min"].get() == 1:
            if self.psd_min is None:
                self.psd_min = np.repeat(np.inf, len(psd))
            self.psd_min[psd < self.psd_min] = psd[psd < self.psd_min]
            line_min = self.view.ax("psd").plot(freq, self.psd_min, name="psd_min", color="b")
        else:
            line_min = None
        line_psd = self.view.ax("psd").plot(freq, psd, name="psd", color="y")

    def _plot_spectrogram(self, freq, psd):
        self.view.ax("spg").ax.set_title("Spectrogram")
        self.psds = np.roll(self.psds, 1, axis=0)
        self.psds[0,:] = psd
        # print(self.psds.shape)
        im = self.view.ax("spg").imshow(
            self.psds, name="spg",
            vmin=self.y_btm, vmax=self.y_top,
            aspect="auto", origin="upper",
            interpolation="nearest", resample=False, rasterized=True
        )

    def __init_psd(self):
        self.view.settings["show_min"].set(1)
        self.view.wg_sets["show_min"].configure(command=self.toggle_psd_min)
        self.view.settings["show_max"].set(1)
        self.view.wg_sets["show_max"].configure(command=self.toggle_psd_max)

        self.view.ax("psd").ax.set_autoscale_on(False)
        self.view.ax("psd").ax.locator_params(axis="x", nbins=5)
        self.view.ax("psd").ax.locator_params(axis="y", nbins=10)
        self.view.ax("psd").ax.grid(True, alpha=0.2)

    def __init_spectrogram(self):
        self.view.settings["max_count"].set(str(self.max_count))
