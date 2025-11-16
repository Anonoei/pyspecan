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
    ref_level = 0
    scale_div = 10.0
    vbw = 10.0
    window = "blackman"

def define_args(parser: argparse.ArgumentParser):
    parser.add_argument("-rl", "--ref_level", default=PlotConfig.ref_level, type=float, help="ref Level")
    parser.add_argument("-sd", "--scale_div", default=PlotConfig.scale_div, type=float, help="scale per division")
    parser.add_argument("-vb", "--vbw", default=PlotConfig.vbw, type=float, help="video bandwidth")
    parser.add_argument("-w", "--window", default=PlotConfig.window, choices=[k for k in WindowLUT.keys()], help="FFT window function")

class SPG3D(FreqPlotController):
    def __init__(self, parent, pane: Panel, **kwargs):
        self.max_count = 20
        self.cur_count = 0
        self.psds: np.ndarray = None # type: ignore

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
        self.f = np.arange(self.parent.model.nfft)
        self.t = np.arange(self.max_count)
        self.x, self.y = np.meshgrid(self.f, self.t)
        self.reset()
        fig = plt.figure(figsize=(5,5), layout="constrained", dpi=100)

        fig.canvas = FigureCanvasTkAgg(fig, master=self.fr_canv)
        self.plotter = BlitPlot(fig) # type: ignore
        # self.plotter = Plot(fig) # type: ignore
        self.plotter.canvas.draw()
        self.plotter.canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True) # type: ignore
        self.plotter.add_ax("spg", fig.add_subplot(projection="3d"))

        # self.plotter.ax("spg").ax.set_autoscale_on(False)
        self.plotter.ax("spg").set_xlim(0, self.parent.model.nfft)
        self.plotter.ax("spg").set_ylim(0, self.max_count)
        self.plotter.ax("spg").ax.locator_params(axis="x", nbins=5)
        self.plotter.ax("spg").ax.locator_params(axis="y", nbins=5)

        self.set_y()
        self.update()

    def reset(self):
        self.psds = np.zeros((self.max_count, self.parent.model.nfft), dtype=np.float32)
        self.psds[:,:] = -np.inf

    def _plot(self, samps):
        psd = self.psd(samps)
        self.plotter.ax("spg").ax.set_title("Spectrogram 3D")
        self.psds = np.roll(self.psds, 1, axis=0)
        self.psds[0,:] = psd
        # if self.cur_count < self.max_count:
        #     self.f = np.arange(0, self.parent.model.nfft)
        #     self.t = np.arange(self.cur_count)
        #     self.x, self.y = np.meshgrid(self.f, self.t)
        #     psds = self.psds[:self.cur_count]
        #     self.cur_count += 1
        # else:
        #     psds = self.psds
        # self.plotter.ax("spg").cla()
        # self.plotter.ax("spg").fig.canvas.draw()

        #self.plotter.ax("spg").set_ylim(self.cur_count - self.max_count, self.cur_count)

        surf = self.plotter.ax("spg").plot_surface(
            self.x, self.y, self.psds,
            cmap="viridis", alpha=0.2,
            rcount=1, ccount=256,
            antialiased=False, shade=True
        )
        self.cur_count += 1

        # surf = self.plotter.ax("spg").plot_wireframe(
        #     self.x, self.y, self.psds[::-1],
        #     rcount=0, ccount=64, alpha=0.5
        # )
        # self.plotter.ax("spg").ax.contourf(self.x, self.y, self.psds[::-1], zdir="x", offset=self.f[0], cmap="coolwarm")
        # self.plotter.ax("spg").ax.contourf(self.x, self.y, self.psds, zdir='y', offset=len(self.psds), cmap="coolwarm")
        # self.plotter.ax("spg").ax.contourf(self.x, self.y, self.psds, zdir="z", offset=np.min(self.psds), cmap="coolwarm")
        self.update()

    def update_f(self, f):
        fmin, fmax, fnum = f
        if self.fmin == fmin and self.fmax == fmax:
            return
        else:
            self.fmin = fmin
            self.fmax = fmax
        #psd_tick = np.linspace(fmin, fmax, 5)
        #psd_text = [str(Frequency.get(f)) for f in psd_tick]

        #spg_tick = np.linspace(0, fnum+1, 5)
        #spg_text = psd_text
        #self.plotter.ax("spg").ax.set_xlim(0, fnum)
        #self.plotter.ax("spg").ax.set_xticks(spg_tick, spg_text)

    def update_nfft(self, nfft):
        self.psds = np.zeros((self.max_count, nfft), dtype=np.float32)
        self.psds[:,:] = -np.inf
        f = np.arange(0, nfft)
        t = np.arange(self.max_count)
        self.x, self.y = np.meshgrid(f, t)
        self.reset()

    def set_y(self):
        """Set plot ylimits"""
        #self.plotter.ax("spg").set_ylim(self.max_count, 0)

    def draw_settings(self, row=0):
        row = super().draw_settings(row)
        var_max_count = tk.StringVar(self.pane.settings, str(self.max_count))
        ent_max_count = ttk.Entry(self.pane.settings, textvariable=var_max_count, width=10)
        ent_max_count.bind("<Return>", self.handle_event)

        self.pane.wgts["max_count"] = ent_max_count
        self.pane.sets["max_count"] = var_max_count

        ttk.Separator(self.pane.settings, orient=tk.HORIZONTAL).grid(row=row,column=0,columnspan=3, pady=5, sticky=tk.EW)
        row += 1
        ttk.Label(self.pane.settings, text="Spectrogram").grid(row=row, column=0,columnspan=2)
        row += 1
        ttk.Label(self.pane.settings, text="Max Count").grid(row=row, column=0)
        ent_max_count.grid(row=row, column=1)
        row += 1
        return row

    # --- GUI bind events and setters --- #
    def handle_event(self, event):
        if event.widget == self.pane.wgts["max_count"]:
            self.set_count(self.pane.sets["max_count"].get())
        else:
            super().handle_event(event)

    def set_count(self, count):
        prev = int(self.max_count)
        try:
            count = int(count)
            self.max_count = count
        except ValueError:
            count = self.max_count
        self.pane.sets["count"].set(str(self.max_count))
        if not prev == self.max_count:
            self.reset()

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
            self.psd_min = None
            self.psd_max = None
