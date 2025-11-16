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
class Phasor(TimePlotController):
    def __init__(self, parent, pane: Panel, **kwargs):
        super().__init__(parent, pane, **kwargs)
        fig = plt.figure(figsize=(5,5), layout="constrained")

        fig.canvas = FigureCanvasTkAgg(fig, master=self.fr_canv)
        self.plotter = BlitPlot(fig) # type: ignore
        self.plotter.canvas.draw()
        self.plotter.canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True) # type: ignore
        self.plotter.add_ax("iq", fig.add_subplot())

        self.plotter.ax("iq").ax.set_autoscale_on(False)
        self.plotter.ax("iq").ax.grid(True, alpha=0.2)
        self.plotter.ax("iq").set_xlim(-1, 1)
        self.plotter.ax("iq").set_ylim(-1, 1)
        self.plotter.ax("iq").ax.set_box_aspect(1)

        self.update()

    def reset(self):
        self.y_max = 0

    def _plot(self, samps):
        s_max = np.max((samps.real, samps.imag))
        self.plotter.ax("iq").ax.set_title(f"Phasor (norm {s_max:03.2f})")
        samps = samps / s_max

        self.plotter.ax("iq").scatter(
            samps.real, samps.imag, name="iq",
            linestyle=None, marker=".", linewidth=0,
        )

        self.update()

    def draw_settings(self, row=0):
        pass
