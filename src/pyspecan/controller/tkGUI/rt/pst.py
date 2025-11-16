import argparse
import tkinter as tk
from tkinter import ttk

import numpy as np

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from ..panels import Panel
from ..plot_base import FreqPlotControllerRT

from ....utils import matrix
from ....backend.mpl.color import cmap
from ....utils.window import WindowLUT
from ....backend.mpl.plot import _Plot, Plot, BlitPlot

class PlotConfig:
    ref_level = 0
    scale_div = 10.0
    vbw = 0.0
    window = "blackman"
    overlap = 0.6
    x = 1001
    y = 600
    cmap = "hot"

def define_args(parser: argparse.ArgumentParser):
    parser.add_argument("-rl", "--ref_level", default=PlotConfig.ref_level, type=float, help="ref Level")
    parser.add_argument("-sd", "--scale_div", default=PlotConfig.scale_div, type=float, help="scale per division")
    parser.add_argument("-vb", "--vbw", default=PlotConfig.vbw, type=float, help="video bandwidth")
    parser.add_argument("-w", "--window", default=PlotConfig.window, choices=[k for k in WindowLUT.keys()], help="FFT window function")

class PST(FreqPlotControllerRT):
    def __init__(self, parent, pane: Panel, **kwargs):
        self.x = kwargs.get("x", PlotConfig.x)
        self.y = kwargs.get("y", PlotConfig.y)
        self.cmap = kwargs.get("cmap", PlotConfig.cmap)
        self.fmin = None
        self.fmax = None
        if not "ref_level" in kwargs:
            kwargs["ref_level"] = PlotConfig.ref_level
        if not "scale_div" in kwargs:
            kwargs["scale_div"] = PlotConfig.scale_div
        if not "vbw" in kwargs:
            kwargs["vbw"] = PlotConfig.vbw
        if not "window" in kwargs:
            kwargs["vbw"] = PlotConfig.vbw
        if not "overlap" in kwargs:
            kwargs["overlap"] = PlotConfig.overlap
        super().__init__(parent, pane, **kwargs)
        self._cmap_set = False
        self._cb_drawn = False

        fig = plt.figure(figsize=(5,5), layout="constrained")

        fig.canvas = FigureCanvasTkAgg(fig, master=self.fr_canv)
        self.plotter = BlitPlot(fig) # type: ignore
        self.plotter.canvas.draw()
        self.plotter.canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True) # type: ignore
        self.plotter.add_ax("pst", fig.add_subplot())

        self.plotter.ax("pst").ax.set_autoscale_on(False)
        self.plotter.ax("pst").ax.locator_params(axis="x", nbins=5)
        self.plotter.ax("pst").ax.locator_params(axis="y", nbins=10)
        self.plotter.ax("pst").ax.grid(True, alpha=0.2)

        self.set_y()
        self.update()

    def reset(self):
        pass

    def _plot(self, samps):
        psd = self.psd(samps)
        self.plotter.ax("pst").ax.set_title(f"Persistent - {psd.shape[1]} FFTs")

        mat = matrix.cvec(self.x, self.y, psd, self.y_top, self.y_btm)
        mat = mat / np.max(mat)

        im = self.plotter.ax("pst").imshow(
                mat, name="mat", cmap=cmap[self.cmap],
                vmin=0, vmax=1,
                aspect="auto",
                interpolation="nearest", resample=False, rasterized=True
        )

        if not self._cb_drawn:
            # print("Adding colorbar")
            cb = self.plotter.fig.colorbar(
                im, ax=self.plotter.ax("pst").ax, # type: ignore
                pad=0.005, fraction=0.05
            )
            self.plotter.canvas.draw()
            self._cb_drawn = True

        if self._cmap_set:
            self.plotter.ax("pst").set_ylim(0, self.y)
            self._cmap_set = False

        self._show_y_location(psd)
        self.update()

    def update_f(self, f):
        fmin, fmax, fnum = f
        if self.fmin == fmin and self.fmax == fmax:
            return
        else:
            self.fmin = fmin
            self.fmax = fmax
        x_mul = [0.0,0.25,0.5,0.75,1.0]

        x_tick = [self.x*m for m in x_mul]
        x_text = [f"{m-self.x/2:.1f}" for m in x_tick]
        self.plotter.ax("pst").ax.set_xticks(x_tick, x_text)
        self.plotter.ax("pst").set_xlim(0, self.x)
        self.update()

    def update_nfft(self, nfft):
        self.reset()

    def set_y(self):
        """Set plot ylimits"""
        y_mul = [0.0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0]
        y_max = self.y_top
        y_min = self.y_btm
        y_rng = abs(y_max - y_min)
        #y_off = y_min if y_min < 0 else -y_min
        y_off = y_min

        y_tick = [self.y*m for m in y_mul]
        y_text = [f"{(y_rng*m)+y_off:.1f}" for m in y_mul]
        self.plotter.ax("pst").ax.set_yticks(y_tick, y_text)
        self.plotter.ax("pst").set_ylim(0, self.y)

    def draw_settings(self, row=0):
        row = super().draw_settings(row)

        var_cmap = tk.StringVar(self.pane.settings, str(self.cmap))
        cb_cmap = ttk.Combobox(self.pane.settings, textvariable=var_cmap, width=9)
        cb_cmap.configure(values=[k for k in cmap.keys()])
        cb_cmap.bind("<<ComboboxSelected>>", self.handle_event)

        self.pane.wgts["cmap"] = cb_cmap
        self.pane.sets["cmap"] = var_cmap

        ttk.Separator(self.pane.settings, orient=tk.HORIZONTAL).grid(row=row,column=0,columnspan=3, pady=5, sticky=tk.EW)
        row += 1
        ttk.Label(self.pane.settings, text="Colors").grid(row=row, column=0)
        cb_cmap.grid(row=row, column=1)
        row += 1
        return row

    # --- GUI bind events and setters --- #
    def handle_event(self, event):
        if event.widget == self.pane.wgts["cmap"]:
            self.set_cmap(self.pane.sets["cmap"].get())
        else:
            super().handle_event(event)
    def set_scale(self, scale):
        prev = self.scale
        super().set_scale(scale)
        if not prev == self.scale:
            self.set_y()

    def set_ref_level(self, ref):
        prev = self.ref_level
        super().set_ref_level(ref)
        if not prev == self.ref_level:
            self.set_y()

    def set_vbw(self, smooth):
        prev = float(self.vbw)
        super().set_vbw(smooth)
        if not prev == self.vbw:
            pass

    def set_cmap(self, _cmap):
        """Set plot color mapping"""
        self.cmap = _cmap
        self._cmap_set = True
