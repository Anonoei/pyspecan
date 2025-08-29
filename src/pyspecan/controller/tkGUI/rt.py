"""Controller for RT mode"""
import numpy as np
# import tkinter as tk
# from tkinter import ttk

# from .base import GUIFreqPlot
from .base import FreqPlotController

from ...utils import matrix
from ...plot.mpl.color import cmap

class ControllerRT(FreqPlotController):
    """Controller for ViewRT"""
    __slots__ = (
        "x", "y", "cmap",
        "_cmap_set", "_cb_drawn"
    )
    def __init__(self, view):
        super().__init__(view, vbw=5.0)
        # self.view: viewPSD = self.view # type hint
        self.x = 1001
        self.y = 600
        self.cmap = "hot"
        self._cmap_set = False
        self._cb_drawn = False

        self.view.settings["cmap"].set(self.cmap)
        self.view.wg_sets["cmap"].configure(values=[k for k in cmap.keys()])
        self.view.wg_sets["cmap"].bind("<<ComboboxSelected>>", self.set_cmap)

        self.view.plotter.ax(0).set_autoscale_on(False)
        # self.view.plotter.ax(0).set_frame_on(False)

        self.set_x()
        self.set_y()

    def set_x(self):
        """Set plot xticks and xlabels"""
        x_mul = [0.0,0.25,0.5,0.75,1.0]

        x_tick = [self.x*m for m in x_mul]
        x_text = [f"{m-self.x/2:.1f}" for m in x_tick]
        self.view.plotter.ax(0).set_xticks(x_tick, x_text)
        self.view.plotter.set_xlim(0, 0, self.x)

    def set_y(self):
        """Set plot yticks and ylabels"""
        y_mul = [0.0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0]
        y_max = self.y_top
        y_min = self.y_btm
        y_rng = abs(abs(y_max) - abs(y_min))
        y_off = y_min if y_min < 0 else -y_min

        y_tick = [self.y*m for m in y_mul]
        y_text = [f"{(y_rng*m)+y_off:.1f}" for m in y_mul]
        self.view.plotter.ax(0).set_yticks(y_tick, y_text)
        self.view.plotter.set_ylim(0, 0, self.y)

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

    def _plot_persistent(self, freq, psds):
        self.view.plotter.ax(0).set_title("Persistent")
        mat = matrix.cvec(self.x, self.y, psds, self.y_top, self.y_btm)
        mat = mat / np.max(mat)

        im = self.view.imshow(
                0, mat, name="mat", cmap=cmap[self.cmap],
                vmin=0, vmax=1,
                aspect="auto",
                interpolation="nearest", resample=False, rasterized=True
        )

        if not self._cb_drawn:
            # print("Adding colorbar")
            cb = self.view.plotter.fig.colorbar(
                im, ax=self.view.plotter.ax(0),
                pad=0.005, fraction=0.05
            )
            self.view.plotter.canvas.draw()
            self._cb_drawn = True

        if self._cmap_set:
            self.view.plotter.set_ylim(0, 0, self.y)
            self._cmap_set = False
