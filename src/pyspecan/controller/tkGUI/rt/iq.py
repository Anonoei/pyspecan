import argparse
import tkinter as tk
from tkinter import ttk

import numpy as np

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from ..panels import Panel
from ..plot_base import TimePlotController

from ....utils import ComplexPMF
from ....backend.mpl.plot import _Plot, Plot, BlitPlot

class PlotConfig:
    pass

def define_args(parser: argparse.ArgumentParser):
    pass
class IQ(TimePlotController):
    def __init__(self, parent, pane: Panel, **kwargs):
        self.y_max = 0
        self.x_arr = np.arange(0, dtype=np.float16)
        super().__init__(parent, pane, **kwargs)
        fig = plt.figure(figsize=(5,5), layout="constrained")

        fig.canvas = FigureCanvasTkAgg(fig, master=self.fr_canv)
        self.plotter = BlitPlot(fig) # type: ignore
        self.plotter.canvas.draw()
        self.plotter.canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True) # type: ignore
        self.plotter.add_ax("iq", fig.add_subplot())

        self.plotter.ax("iq").ax.set_autoscale_on(False)
        self.plotter.ax("iq").ax.grid(True, alpha=0.2)

        self.update()

    def reset(self):
        self.y_max = 0

    def _plot(self, samps):
        self.plotter.ax("iq").ax.set_title("IQ")
        prev_max = self.y_max
        self.y_max = np.max((self.y_max, -np.min(samps.real), np.max(samps.real), -np.min(samps.imag), np.max(samps.imag)))
        if not self.y_max == prev_max:
            self.plotter.ax("iq").set_ylim(-self.y_max, self.y_max)
        s_len = len(samps)
        if not s_len == len(self.x_arr):
            self.x_arr = np.arange(s_len) / s_len
            self.plotter.ax("iq").set_xlim(0, 1)

        line_real = self.plotter.ax("iq").plot(self.x_arr, samps.real, name="real")
        line_imag = self.plotter.ax("iq").plot(self.x_arr, samps.imag, name="imag")

        self.update()

    def draw_settings(self, row=0):
        pass
