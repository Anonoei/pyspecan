"""GUI view RT mode plots"""
import tkinter as tk
from tkinter import ttk

import matplotlib.pyplot as plt

# from ...plot.mpl.base import BlitPlot
from .base import GUIFreqPlot

class ViewRT(GUIFreqPlot):
    """Manager for RT mode plots"""
    def __init__(self, view, root):
        fig = plt.figure(figsize=(5,5), layout="constrained")
        super().__init__(view, root, fig)
        self.gs = self.plotter.fig.add_gridspec(1,1)
        self.plotter.add_ax("pst", fig.add_subplot(self.gs[0]))
        self.gs.update()

    def draw_settings(self, parent, row=0):
        row = super().draw_settings(parent, row)

        var_cmap = tk.StringVar(self.fr_sets)
        cb_cmap = ttk.Combobox(self.fr_sets, textvariable=var_cmap, width=9)

        self.wg_sets["cmap"] = cb_cmap
        self.settings["cmap"] = var_cmap

        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(row=row,column=0,columnspan=3, pady=5, sticky=tk.EW)
        row += 1
        ttk.Label(parent, text="Colors").grid(row=row, column=0)
        cb_cmap.grid(row=row, column=1)
        row += 1
        return row
