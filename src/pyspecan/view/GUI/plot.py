import tkinter as tk
from tkinter import ttk

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import (FigureCanvasTkAgg, NavigationToolbar2Tk)

import numpy as np

from ...plot.plot import Plot, BlitPlot

class GUIPlot:
    def __init__(self, view, root, plotter=Plot):
        fig, ax = plt.subplots(figsize=(10,10), dpi=100, layout="tight")

        self.view = view
        self._root = root
        self.settings = {}
        self.ready = False

        self.fr_main = tk.Frame(root, highlightbackground="black",highlightthickness=1)

        self.fr_sets = tk.Frame(self.fr_main)
        self.wg_sets = {}
        self.draw_settings(self.fr_sets)
        self.fr_sets.pack(side=tk.LEFT, fill=tk.Y)
        self.fr_sets.pack_forget()

        self.fr_canv = tk.Frame(self.fr_main, bg="white")
        self.fr_canv.pack(fill=tk.BOTH, expand=True)
        fig.canvas = FigureCanvasTkAgg(fig, master=self.fr_canv)
        self._plot = plotter(fig)
        # toolbar = NavigationToolbar2Tk(canvas, root)
        # toolbar.update()
        self._plot.canvas.draw()
        self._plot.canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.btn_toggle = tk.Button(self.fr_canv, text="Settings",
                font=("Arial", 8), command=self.toggle_settings, bg="white", fg="black")
        self.btn_toggle.place(relx=0.0, rely=0.0, width=50, height=20)

        self.fr_main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def draw_settings(self, parent):
        pass

    def toggle_settings(self, *args, **kwargs):
        if self.fr_sets.winfo_ismapped():
            self.fr_sets.forget()
            # self.btn_toggle.config(text="Show Settings")
        else:
            self.fr_sets.pack(side=tk.LEFT, fill=tk.Y, before=self.fr_canv)
            # self.btn_toggle.config(text="Hide Settings")

    def update(self):
        self._plot.update()

    @property
    def fig(self):
        return self._plot.fig

    def ax(self, idx):
        return self._plot.ax(idx)

    def art(self, i, j):
        return self._plot.art(i, j)

    def add_ax(self, *args, **kwargs):
        return self._plot.add_ax(*args,**kwargs)

    def add_artist(self, idx, art):
        return self._plot.add_artist(idx, art)

    def plot(self, idx, *args, **kwargs):
        self._plot.plot(idx, *args, **kwargs)

    def set_data(self, i, j, x, y):
        self._plot.set_data(i, j, x, y)

    def set_xdata(self, i, j, x):
        self._plot.set_xdata(i, j, x)

    def set_ydata(self, i, j, y):
        self._plot.set_ydata(i, j, y)

class GUIBlitPlot(GUIPlot):
    def __init__(self, view, root, plotter=BlitPlot):
        super().__init__(view, root, plotter)
