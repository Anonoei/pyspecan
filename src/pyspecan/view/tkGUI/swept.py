"""GUI view SWEPT mode plots"""
import tkinter as tk
from tkinter import ttk

import matplotlib.pyplot as plt
from matplotlib import gridspec

# from ...plot.mpl.base import BlitPlot
from .base import GUIFreqPlot

class ViewSwept(GUIFreqPlot):
    """Manager for SWEPT mode plots"""
    def __init__(self, view, root):
        fig = plt.figure(figsize=(5,5), layout="constrained")
        super().__init__(view, root, fig)
        self.gs = self.plotter.fig.add_gridspec(2,1)
        self.plotter.add_ax("psd", fig.add_subplot(self.gs[0]))
        self.plotter.add_ax("spg", fig.add_subplot(self.gs[1]))
        self.gs.update()

    def draw_settings(self, parent, row=0):
        var_show_psd = tk.IntVar(self.fr_sets)
        chk_show_psd = ttk.Checkbutton(parent, onvalue=1, offvalue=0,variable=var_show_psd)
        var_show_spg = tk.IntVar(self.fr_sets)
        chk_show_spg = ttk.Checkbutton(parent, onvalue=1, offvalue=0,variable=var_show_spg)

        self.wg_sets["show_psd"] = chk_show_psd
        self.settings["show_psd"] = var_show_psd
        self.wg_sets["show_spg"] = chk_show_spg
        self.settings["show_spg"] = var_show_spg

        ttk.Label(parent, text="Plots").grid(row=row, column=0,columnspan=2)
        row += 1
        ttk.Label(parent, text="PSD").grid(row=row, column=0)
        chk_show_psd.grid(row=row, column=1)
        row += 1
        ttk.Label(parent, text="SPG").grid(row=row, column=0)
        chk_show_spg.grid(row=row, column=1)
        row += 1
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(row=row,column=0,columnspan=3, pady=5, sticky=tk.EW)
        row += 1

        row = super().draw_settings(parent, row)
        # row = self._draw_settings_freq(parent, row)

        row = self._draw_settings_psd(parent, row)

        row = self._draw_settings_spectrogram(parent, row)
        return row

    def _draw_settings_psd(self, parent, row):
        var_psd_min = tk.IntVar(self.fr_sets)
        chk_show_min = ttk.Checkbutton(parent, onvalue=1, offvalue=0,variable=var_psd_min)
        var_psd_max = tk.IntVar(self.fr_sets)
        chk_show_max = ttk.Checkbutton(parent, onvalue=1, offvalue=0, variable=var_psd_max)

        self.wg_sets["show_min"] = chk_show_min
        self.settings["show_min"] = var_psd_min
        self.wg_sets["show_max"] = chk_show_max
        self.settings["show_max"] = var_psd_max

        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(row=row,column=0,columnspan=3, pady=5, sticky=tk.EW)
        row += 1
        ttk.Label(parent, text="PSD").grid(row=row, column=0,columnspan=2)
        row += 1
        ttk.Label(parent, text="Max Hold").grid(row=row, column=0)
        chk_show_max.grid(row=row, column=1)
        row += 1
        ttk.Label(parent, text="Min Hold").grid(row=row, column=0)
        chk_show_min.grid(row=row, column=1)
        row += 1
        return row

    def _draw_settings_spectrogram(self, parent, row):
        var_max_count = tk.StringVar(self.fr_sets)
        ent_max_count = ttk.Entry(self.fr_sets, textvariable=var_max_count, width=10)

        self.wg_sets["max_count"] = ent_max_count
        self.settings["max_count"] = var_max_count

        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(row=row,column=0,columnspan=3, pady=5, sticky=tk.EW)
        row += 1
        ttk.Label(parent, text="Spectrogram").grid(row=row, column=0,columnspan=2)
        row += 1
        ttk.Label(parent, text="Max Count").grid(row=row, column=0)
        ent_max_count.grid(row=row, column=1)
        row += 1
        return row
