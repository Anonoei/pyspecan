import argparse
import tkinter as tk
from tkinter import ttk

import numpy as np

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from ..panels import Panel
from ..plot_base import FreqPlotController

from ....utils import vbw as _vbw
from ....obj import Frequency
from ....utils.window import WindowLUT
from ....backend.mpl.plot import _Plot, Plot, BlitPlot

class PlotConfig:
    ref_level = 50
    scale_div = 5
    vbw = 10.0
    window = "blackman"

def define_args(parser: argparse.ArgumentParser):
    parser.add_argument("-rl", "--ref_level", default=PlotConfig.ref_level, type=float, help="ref Level")
    parser.add_argument("-sd", "--scale_div", default=PlotConfig.scale_div, type=float, help="scale per division")
    parser.add_argument("-vb", "--vbw", default=PlotConfig.vbw, type=float, help="video bandwidth")
    parser.add_argument("-w", "--window", default=PlotConfig.window, choices=[k for k in WindowLUT.keys()], help="FFT window function")

class Freq(FreqPlotController):
    def __init__(self, parent, pane: Panel, **kwargs):
        self.mag_min = None
        self.mag_max = None
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
        super().__init__(parent, pane, **kwargs)
        fig = plt.figure(figsize=(5,5), layout="constrained")

        fig.canvas = FigureCanvasTkAgg(fig, master=self.fr_canv)
        self.plotter = BlitPlot(fig) # type: ignore
        self.plotter.canvas.draw()
        self.plotter.canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True) # type: ignore
        self.plotter.add_ax("mag", fig.add_subplot(2,1,1))
        self.plotter.add_ax("pha", fig.add_subplot(2,1,2))

        self.plotter.ax("mag").ax.set_autoscale_on(False)
        self.plotter.ax("mag").ax.locator_params(axis="x", nbins=5)
        self.plotter.ax("mag").ax.locator_params(axis="y", nbins=10)
        self.plotter.ax("mag").ax.grid(True, alpha=0.2)

        self.plotter.ax("pha").ax.set_autoscale_on(False)
        self.plotter.ax("pha").ax.locator_params(axis="x", nbins=5)
        self.plotter.ax("pha").ax.locator_params(axis="y", nbins=10)
        self.plotter.ax("pha").ax.grid(True, alpha=0.2)

        # self.plotter.fig.set_layout_engine("constrained")
        # self.plotter.fig.get_layout_engine().execute(self.plotter.fig) # type: ignore

        self.set_y()
        self.update()

    def reset(self):
        self.mag_min = None
        self.mag_max = None

    def _plot(self, samps):
        fft = np.fft.fft(samps)
        fft = np.fft.fftshift(fft)
        mag = np.abs(fft)
        pha = np.angle(fft)

        self.plotter.ax("mag").ax.set_title("Freq")

        if self.pane.sets["show_max"].get() == 1:
            if self.mag_max is None:
                self.mag_max = np.repeat(-np.inf, len(mag))
            self.mag_max[mag > self.mag_max] = mag[mag > self.mag_max]
            line_max = self.plotter.ax("mag").plot(self.parent.model.f, self.mag_max, name="max", color="r")
        else:
            line_max = None
        if self.pane.sets["show_min"].get() == 1:
            if self.mag_min is None:
                self.mag_min = np.repeat(np.inf, len(mag))
            self.mag_min[mag < self.mag_min] = mag[mag < self.mag_min]
            line_min = self.plotter.ax("mag").plot(self.parent.model.f, self.mag_min, name="min", color="b")
        else:
            line_min = None
        line_mag = self.plotter.ax("mag").plot(self.parent.model.f, mag, name="fft", color="y")
        line_pha = self.plotter.ax("pha").plot(self.parent.model.f, pha, name="pha", color="b")

        self._show_y_location(mag)
        self.update()

    def update_f(self, f):
        fmin, fmax, fnum = f
        if self.fmin == fmin and self.fmax == fmax:
            return
        else:
            self.fmin = fmin
            self.fmax = fmax
        mag_tick = np.linspace(fmin, fmax, 5)
        mag_text = [str(Frequency.get(f)) for f in mag_tick]
        self.plotter.ax("mag").set_xlim(fmin, fmax)
        self.plotter.ax("mag").ax.set_xticks(mag_tick, mag_text)
        self.plotter.ax("pha").set_xlim(fmin, fmax)
        self.plotter.ax("pha").ax.set_xticks(mag_tick, mag_text)
        self.update()

    def update_nfft(self, nfft):
        self.reset()

    def set_y(self):
        """Set plot ylimits"""
        self.plotter.ax("mag").set_ylim(self.y_btm, self.y_top)
        self.plotter.ax("pha").set_ylim(-4, 4)

    def draw_settings(self, row=0):
        row = super().draw_settings(row)
        var_psd_min = tk.IntVar(self.pane.settings, 1)
        chk_show_min = ttk.Checkbutton(self.pane.settings, onvalue=1, offvalue=0,variable=var_psd_min)
        chk_show_min.configure(command=self.toggle_psd_min)
        var_psd_max = tk.IntVar(self.pane.settings, 1)
        chk_show_max = ttk.Checkbutton(self.pane.settings, onvalue=1, offvalue=0, variable=var_psd_max)
        chk_show_max.configure(command=self.toggle_psd_max)

        self.pane.wgts["show_min"] = chk_show_min
        self.pane.sets["show_min"] = var_psd_min
        self.pane.wgts["show_max"] = chk_show_max
        self.pane.sets["show_max"] = var_psd_max

        ttk.Separator(self.pane.settings, orient=tk.HORIZONTAL).grid(row=row,column=0,columnspan=3, pady=5, sticky=tk.EW)
        row += 1
        ttk.Label(self.pane.settings, text="FFT Magnitude").grid(row=row, column=0,columnspan=2)
        row += 1
        ttk.Label(self.pane.settings, text="Max Hold").grid(row=row, column=0)
        chk_show_max.grid(row=row, column=1)
        row += 1
        ttk.Label(self.pane.settings, text="Min Hold").grid(row=row, column=0)
        chk_show_min.grid(row=row, column=1)
        row += 1
        return row

    # --- GUI bind events and setters --- #
    def set_scale(self, scale):
        prev = float(self.scale)
        super().set_scale(scale)
        if not prev == self.scale:
            self.set_y()

    def set_ref_level(self, ref):
        prev = float(self.ref_level)
        super().set_ref_level(ref)
        if not prev == self.ref_level:
            self.set_y()

    def set_vbw(self, smooth):
        prev = float(self.vbw)
        super().set_vbw(smooth)
        if not prev == self.vbw:
            self.mag_min = None
            self.mag_max = None

    def toggle_psd_min(self):
        """Toggle PSD min-hold visibility"""
        art = self.plotter.ax("mag").art("min")
        if art is None:
            return
        if self.pane.sets["show_min"].get() == 0:
            self.mag_max = None
            art.set_visible(False)
        else:
            art.set_visible(True)
        self.update()

    def toggle_psd_max(self):
        """Toggle PSD max-hold visibility"""
        art = self.plotter.ax("mag").art("max")
        if art is None:
            return
        if self.pane.sets["show_max"].get() == 0:
            self.mag_min = None
            art.set_visible(False)
        else:
            art.set_visible(True)
        self.update()
