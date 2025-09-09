"""Base Views for tkGUI View plots"""
import tkinter as tk
from tkinter import ttk

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
# from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk

from ...backend.mpl.plot import _Plot, Plot, BlitPlot


class GUIPlot:
    """tkinter wrapper for pyspecan.backend.mpl.plot"""
    __slots__ = (
        "view", "_root", "plotter", "settings", "ready",
        "fr_main", "fr_canv", "fr_sets", "btn_toggle",
        "wg_sets",
    )
    def __init__(self, view, root, fig: Figure, plotter=_Plot):
        if plotter is _Plot:
            plotter = Plot
        self.view = view
        self._root = root
        self.settings = {}
        self.ready = False

        self.fr_main = ttk.Frame(root)

        self.fr_sets = ttk.Frame(self.fr_main)
        self.wg_sets = {}
        self.draw_settings(self.fr_sets)
        self.fr_sets.pack(side=tk.LEFT, fill=tk.Y)
        self.fr_sets.pack_forget()

        self.fr_canv = ttk.Frame(self.fr_main)
        self.fr_canv.pack(fill=tk.BOTH, expand=True)
        fig.canvas = FigureCanvasTkAgg(fig, master=self.fr_canv)
        self.plotter = plotter(fig)
        # toolbar = NavigationToolbar2Tk(canvas, root)
        # toolbar.update()
        self.plotter.canvas.draw()
        self.plotter.canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True) # type: ignore

        self.btn_toggle = ttk.Button(self.fr_canv, text="Settings", style="Settings.TButton")
        self.btn_toggle.place(relx=0.0, rely=0.0, width=50, height=25)

        self.fr_main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    @property
    def fig(self):
        return self.plotter.fig
    def ax(self, name):
        return self.plotter.ax(name)
    def add_ax(self, *args, **kwargs):
        return self.plotter.add_ax(*args,**kwargs)

    def draw_settings(self, parent, row=0):
        """Initialize settings panel"""
        raise NotImplementedError()

class GUIBlitPlot(GUIPlot):
    """tkinter wrapper for pyspecan.plot.mpl BlitPlot"""
    def __init__(self, view, root, fig):
        super().__init__(view, root, fig, BlitPlot)


class GUIFreqPlot(GUIBlitPlot):
    """Frequency domain view helpers"""
    __slots__ = ("lbl_lo", "lbl_hi")
    def __init__(self, view, root, fig):
        super().__init__(view, root, fig)

        self.lbl_lo = ttk.Label(self.fr_canv, text="V")
        self.lbl_hi = ttk.Label(self.fr_canv, text="^")

    def draw_settings(self, parent, row=0):
        var_scale = tk.StringVar(self.fr_sets)
        ent_scale = ttk.Entry(self.fr_sets, textvariable=var_scale, width=10)

        var_ref_level = tk.StringVar(self.fr_sets)
        ent_ref_level = ttk.Entry(self.fr_sets, textvariable=var_ref_level, width=10)

        var_vbw = tk.StringVar(self.fr_sets)
        ent_vbw = ttk.Entry(self.fr_sets, textvariable=var_vbw, width=10)

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

        ttk.Label(parent, text="Scale/Div").grid(row=row, column=0)
        ent_scale.grid(row=row, column=1)
        row += 1
        ttk.Label(parent, text="Ref Level").grid(row=row, column=0)
        ent_ref_level.grid(row=row, column=1)
        row += 1
        ttk.Label(parent, text="VBW").grid(row=row, column=0)
        ent_vbw.grid(row=row, column=1)
        row += 1
        ttk.Label(parent, text="Window").grid(row=row, column=0)
        cb_window.grid(row=row, column=1)
        row += 1
        return row
