"""Controller for RT mode"""
import numpy as np
# import tkinter as tk
# from tkinter import ttk

# from .base import GUIFreqPlot
from .base import FreqPlotController

from ...utils import matrix
from ...backend.mpl.color import cmap

class ControllerRT(FreqPlotController):
    """Controller for ViewRT"""
    __slots__ = (
        "x", "y", "cmap",
        "_cmap_set", "_cb_drawn"
    )
    def __init__(self, view, ref_level=0.0, scale=10.0, vbw=5.0, window="blackman"):
        self.x = 1001
        self.y = 600
        super().__init__(view, ref_level, scale, vbw, window)
        # self.view: viewPSD = self.view # type hint
        self.cmap = "hot"
        self._cmap_set = False
        self._cb_drawn = False

        self.view.settings["cmap"].set(self.cmap)
        self.view.wg_sets["cmap"].configure(values=[k for k in cmap.keys()])
        self.view.wg_sets["cmap"].bind("<<ComboboxSelected>>", self.set_cmap)

        self.view.ax("pst").ax.set_autoscale_on(False)
        self.view.ax("pst").ax.locator_params(axis="x", nbins=5)
        self.view.ax("pst").ax.locator_params(axis="y", nbins=10)
        self.view.ax("pst").ax.grid(True, alpha=0.2)

        self.set_y()

    def update_f(self, f):
        fmin, fmax, fnum = f
        """Set plot xticks and xlabels"""
        x_mul = [0.0,0.25,0.5,0.75,1.0]

        x_tick = [self.x*m for m in x_mul]
        x_text = [f"{m-self.x/2:.1f}" for m in x_tick]
        self.view.ax("pst").ax.set_xticks(x_tick, x_text)
        self.view.ax("pst").set_xlim(0, self.x)

    def set_y(self):
        """Set plot yticks and ylabels"""
        y_mul = [0.0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0]
        y_max = self.y_top
        y_min = self.y_btm
        y_rng = abs(abs(y_max) - abs(y_min))
        y_off = y_min if y_min < 0 else -y_min

        y_tick = [self.y*m for m in y_mul]
        y_text = [f"{(y_rng*m)+y_off:.1f}" for m in y_mul]
        self.view.ax("pst").ax.set_yticks(y_tick, y_text)
        self.view.ax("pst").set_ylim(0, self.y)

    def set_scale(self, *args, **kwargs):
        prev = self.scale
        super().set_scale(*args, **kwargs)
        if not prev == self.scale:
            self.set_y()

    def set_ref_level(self, *args, **kwargs):
        prev = self.ref_level
        super().set_ref_level(*args, **kwargs)
        if not prev == self.ref_level:
            self.set_y()

    def set_cmap(self, *args, **kwargs):
        """Set plot color mapping"""
        self.cmap = self.view.settings["cmap"].get()
        self._cmap_set = True

    def plot(self, freq, psd):
        self._plot_persistent(freq, psd)

        self._show_y_location(psd)
        self.update()

    def _plot_persistent(self, freq, psds):
        self.view.ax("pst").ax.set_title("Persistent")
        mat = matrix.cvec(self.x, self.y, psds, self.y_top, self.y_btm)
        mat = mat / np.max(mat)

        im = self.view.ax("pst").imshow(
                mat, name="mat", cmap=cmap[self.cmap],
                vmin=0, vmax=1,
                aspect="auto",
                interpolation="nearest", resample=False, rasterized=True
        )

        if not self._cb_drawn:
            # print("Adding colorbar")
            cb = self.view.plotter.fig.colorbar(
                im, ax=self.view.ax("pst").ax,
                pad=0.005, fraction=0.05
            )
            self.view.plotter.canvas.draw()
            self._cb_drawn = True

        if self._cmap_set:
            self.view.ax("pst").set_ylim(0, self.y)
            self._cmap_set = False
