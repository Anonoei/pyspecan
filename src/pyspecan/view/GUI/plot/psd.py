import tkinter as tk
from tkinter import ttk

from .base import GUIFreqPlot

class PSD(GUIFreqPlot):
    def draw_settings(self, parent, row=0):
        row = super().draw_settings(parent, row)
        var_psd_min = tk.IntVar(self.fr_sets)
        chk_show_min = tk.Checkbutton(parent, onvalue=1, offvalue=0,variable=var_psd_min)

        var_psd_max = tk.IntVar(self.fr_sets)
        chk_show_max = tk.Checkbutton(parent, onvalue=1, offvalue=0, variable=var_psd_max)

        self.wg_sets["show_min"] = chk_show_min
        self.settings["show_min"] = var_psd_min
        self.wg_sets["show_max"] = chk_show_max
        self.settings["show_max"] = var_psd_max

        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(row=row,column=0,columnspan=3, pady=5, sticky=tk.EW)
        row += 1
        tk.Label(parent, text="Max Hold").grid(row=row, column=0)
        chk_show_max.grid(row=row, column=1)
        row += 1
        tk.Label(parent, text="Min Hold").grid(row=row, column=0)
        chk_show_min.grid(row=row, column=1)
        row += 1
        return row
