import tkinter as tk
from tkinter import ttk

from ...plot.base import BlitPlot
from .base import GUIFreqPlot

class ViewSwept(GUIFreqPlot):
    def __init__(self, view, root):
        super().__init__(view, root, BlitPlot,
            figsize=(10,10), dpi=100,
            nrows=2,ncols=1, layout="tight"
        )
    def draw_settings(self, parent, row=0):
        row = super().draw_settings(parent, row)
        # row = self._draw_settings_freq(parent, row)
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(row=row,column=0,columnspan=3, pady=5, sticky=tk.EW)
        row += 1

        row = self._draw_settings_psd(parent, row)
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(row=row,column=0,columnspan=3, pady=5, sticky=tk.EW)
        row += 1

        row = self._draw_settings_spectrogram(parent, row)
        return row

    def _draw_settings_psd(self, parent, row):
        var_psd_min = tk.IntVar(self.fr_sets)
        chk_show_min = tk.Checkbutton(parent, onvalue=1, offvalue=0,variable=var_psd_min)

        var_psd_max = tk.IntVar(self.fr_sets)
        chk_show_max = tk.Checkbutton(parent, onvalue=1, offvalue=0, variable=var_psd_max)

        self.wg_sets["show_min"] = chk_show_min
        self.settings["show_min"] = var_psd_min
        self.wg_sets["show_max"] = chk_show_max
        self.settings["show_max"] = var_psd_max

        tk.Label(parent, text="Max Hold").grid(row=row, column=0)
        chk_show_max.grid(row=row, column=1)
        row += 1
        tk.Label(parent, text="Min Hold").grid(row=row, column=0)
        chk_show_min.grid(row=row, column=1)
        row += 1
        return row

    def _draw_settings_spectrogram(self, parent, row):
        var_max_count = tk.StringVar(self.fr_sets)
        ent_max_count = tk.Entry(self.fr_sets, textvariable=var_max_count, width=10)

        self.wg_sets["max_count"] = ent_max_count
        self.settings["max_count"] = var_max_count

        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(row=row,column=0,columnspan=3, pady=5, sticky=tk.EW)
        row += 1
        tk.Label(parent, text="Max Count").grid(row=row, column=0)
        ent_max_count.grid(row=row, column=1)
        row += 1
        return row
