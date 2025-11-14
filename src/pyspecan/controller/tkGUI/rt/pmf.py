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
class PMF(TimePlotController):
    def __init__(self, parent, pane: Panel, **kwargs):
        self.pmf = ComplexPMF(256)
        super().__init__(parent, pane, **kwargs)
        fig = plt.figure(figsize=(5,5), layout="constrained")

        fig.canvas = FigureCanvasTkAgg(fig, master=self.fr_canv)
        self.plotter = BlitPlot(fig) # type: ignore
        self.plotter.canvas.draw()
        self.plotter.canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True) # type: ignore
        self.plotter.add_ax("pmf", fig.add_subplot())

        self.plotter.ax("pmf").ax.grid(True, alpha=0.2)

        self.update()

    def reset(self):
        self.pmf = ComplexPMF(256)

    def _plot(self, samps):
        self.plotter.ax("pmf").ax.set_title("PMF")
        self.pmf.update(samps)

        x = self.pmf.x
        y = self.pmf.y

        line_real = self.plotter.ax("pmf").plot(y.real, x.real, name="real")
        line_imag = self.plotter.ax("pmf").plot(y.imag, x.imag, name="imag")

        self.update()

    def draw_settings(self, row=0):
        pass
