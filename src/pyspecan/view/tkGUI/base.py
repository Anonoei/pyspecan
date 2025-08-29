"""Base Views for tkGUI View plots"""
import tkinter as tk
from tkinter import ttk

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
# from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk

from ...plot.mpl.base import Plot, BlitPlot

class GUIPlot:
    """tkinter wrapper for pyspecan.plot.mpl"""
    __slots__ = (
        "view", "_root", "plotter", "settings", "ready",
        "fr_main", "fr_canv", "fr_sets", "btn_toggle",
        "wg_sets",
    )
    def __init__(self, view, root, plotter=Plot, *args, **kwargs):
        fig, ax = plt.subplots(*args, **kwargs)

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
        self.plotter = plotter(fig)
        # toolbar = NavigationToolbar2Tk(canvas, root)
        # toolbar.update()
        self.plotter.canvas.draw()
        self.plotter.canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True) # type: ignore

        self.btn_toggle = tk.Button(self.fr_canv, text="Settings",
                font=("Arial", 8), bg="white", fg="black")
        self.btn_toggle.place(relx=0.0, rely=0.0, width=50, height=20)

        self.fr_main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def draw_settings(self, parent, row=0):
        """Initialize settings panel"""
        raise NotImplementedError()

    @property
    def fig(self):
        return self.plotter.fig

    def ax(self, idx):
        return self.plotter.ax(idx)

    def art(self, i, j):
        return self.plotter.art(i, j)

    def add_ax(self, *args, **kwargs):
        return self.plotter.add_ax(*args,**kwargs)

    def add_artist(self, idx, art, name):
        return self.plotter.add_artist(idx, art, name)

    def plot(self, idx, *args, **kwargs):
        return self.plotter.plot(idx, *args, **kwargs)

    def imshow(self, idx, *args, **kwargs):
        return self.plotter.imshow(idx, *args, **kwargs)

    def set_data(self, i, j, x, y):
        self.plotter.set_data(i, j, x, y)

    def set_xdata(self, i, j, x):
        self.plotter.set_xdata(i, j, x)

    def set_ydata(self, i, j, y):
        self.plotter.set_ydata(i, j, y)

class GUIBlitPlot(GUIPlot):
    """tkinter wrapper for pyspecan.plot.mpl BlitPlot"""
    def __init__(self, view, root, *args, **kwargs):
        super().__init__(view, root, BlitPlot, *args, **kwargs)


class GUIFreqPlot(GUIBlitPlot):
    """Frequency domain view helpers"""
    __slots__ = ("lbl_lo", "lbl_hi")
    def __init__(self, view, root, *args, **kwargs):
        super().__init__(view, root, *args, **kwargs)

        self.lbl_lo = tk.Label(self.fr_canv, text="V")
        self.lbl_hi = tk.Label(self.fr_canv, text="^")

    def draw_settings(self, parent, row=0):
        var_scale = tk.StringVar(self.fr_sets)
        ent_scale = tk.Entry(self.fr_sets, textvariable=var_scale, width=10)

        var_ref_level = tk.StringVar(self.fr_sets)
        ent_ref_level = tk.Entry(self.fr_sets, textvariable=var_ref_level, width=10)

        var_vbw = tk.StringVar(self.fr_sets)
        ent_vbw = tk.Entry(self.fr_sets, textvariable=var_vbw, width=10)

        var_window = tk.StringVar(self.fr_sets)
        cb_window = ttk.Combobox(self.fr_sets, textvariable=var_window, width=9)

        self.wg_sets["scale"] = ent_scale
        self.settings["scale"] = var_scale
        self.wg_sets["ref_level"] = ent_ref_level
        self.settings["ref_level"] = var_ref_level
        self.wg_sets["vbw"] = ent_vbw
        self.settings["vbw"] = var_vbw
        self.wg_sets["window"] = cb_window
        self.settings["window"] = var_window

        tk.Label(parent, text="Scale/Div").grid(row=row, column=0)
        ent_scale.grid(row=row, column=1)
        row += 1
        tk.Label(parent, text="Ref Level").grid(row=row, column=0)
        ent_ref_level.grid(row=row, column=1)
        row += 1
        tk.Label(parent, text="VBW").grid(row=row, column=0)
        ent_vbw.grid(row=row, column=1)
        row += 1
        tk.Label(parent, text="Window").grid(row=row, column=0)
        cb_window.grid(row=row, column=1)
        row += 1
        return row
