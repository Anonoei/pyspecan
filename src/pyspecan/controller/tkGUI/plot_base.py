"""Base Controllers for tkGUI Controller"""
import argparse

import tkinter as tk
from tkinter import ttk

import numpy as np

from .panels import Panel

from ...utils.window import WindowLUT

from ...backend.mpl.plot import _Plot, Plot, BlitPlot

def define_args(parser: argparse.ArgumentParser, cfg):
    parser.add_argument("-rl", "--ref_level", default=cfg.ref_level, type=float, help="ref Level")
    parser.add_argument("-sd", "--scale_div", default=cfg.scale_div, type=float, help="scale per division")
    parser.add_argument("-vb", "--vbw", default=cfg.vbw, type=float, help="video bandwidth")
    parser.add_argument("-w", "--window", default=cfg.window, choices=[k for k in WindowLUT.keys()], help="FFT window function")

class _PlotController:
    """Controller for view.tkGUI.GUIPlot"""
    __slots__ = (
        "parent", "pane", "plotter", "ready",
        "fr_canv"
    )
    def __init__(self, parent, pane: Panel, **kwargs):
        self.parent = parent
        self.pane = pane
        self.ready = False
        self.plotter: Plot = None # type: ignore

        self.fr_canv = ttk.Frame(pane.fr_main)
        self.fr_canv.pack(fill=tk.BOTH, expand=True)

    def update(self):
        """Update view plot"""
        self.plotter.update()

    def reset(self):
        """Reset plot view"""
        pass

    def plot(self, *args, **kwargs):
        """Update plot data"""
        raise NotImplementedError()

    def draw_settings(self, row=0):
        """Initialize settings panel"""
        raise NotImplementedError()

class FreqPlotController(_PlotController):
    """Controller for view.tkGUI.GUIFreqPlot"""
    __slots__ = (
        "window", "vbw", "scale", "ref_level",
        "lbl_lo", "lbl_hi"
    )
    def __init__(self, parent, pane: Panel, **kwargs):
        super().__init__(parent, pane)

        self.window =  kwargs.get("window", "blackman")
        self.vbw = kwargs.get("vbw", 10.0)
        self.scale = kwargs.get("scale_div", 10.0)
        self.ref_level = kwargs.get("ref_level", 0.0)
        self.draw_settings()

        self.set_ref_level(self.pane.sets["ref_level"].get())

        self.lbl_lo = ttk.Label(self.fr_canv, text="V")
        self.lbl_hi = ttk.Label(self.fr_canv, text="^")

    def update(self):
        self.plotter.canvas.draw()

    def update_f(self, f):
        """Set plot xticks and xlabels"""

    def update_nfft(self, nfft):
        """Update plot nfft"""

    def plot(self, freq, psd):
        raise NotImplementedError()

    @property
    def y_top(self):
        """Return plot maximum amplitude"""
        return self.ref_level
    @property
    def y_btm(self):
        """Return plot minimum amplitude"""
        return self.ref_level - (10*self.scale)

    def _show_y_location(self, psd):
        if np.all(psd < self.y_btm):
            self.lbl_lo.place(relx=0.2, rely=0.9, width=20, height=20)
        else:
            if self.lbl_lo.winfo_ismapped():
                self.lbl_lo.place_forget()
        if np.all(psd > self.y_top):
            self.lbl_hi.place(relx=0.2, rely=0.1, width=20, height=20)
        else:
            if self.lbl_hi.winfo_ismapped():
                self.lbl_hi.place_forget()

    def draw_settings(self, row=0):
        var_scale = tk.StringVar(self.pane.settings, str(self.scale))
        ent_scale = ttk.Entry(self.pane.settings, textvariable=var_scale, width=10)
        ent_scale.bind("<Return>", self.handle_event)

        var_ref_level = tk.StringVar(self.pane.settings, str(self.ref_level))
        ent_ref_level = ttk.Entry(self.pane.settings, textvariable=var_ref_level, width=10)
        ent_ref_level.bind("<Return>", self.handle_event)

        var_vbw = tk.StringVar(self.pane.settings, str(self.vbw))
        ent_vbw = ttk.Entry(self.pane.settings, textvariable=var_vbw, width=10)
        ent_vbw.bind("<Return>", self.handle_event)

        var_window = tk.StringVar(self.pane.settings, str(self.window))
        cb_window = ttk.Combobox(self.pane.settings, textvariable=var_window, width=9)
        cb_window.bind("<<ComboboxSelected>>", self.handle_event)

        self.pane.wgts["scale"] = ent_scale
        self.pane.sets["scale"] = var_scale
        self.pane.wgts["ref_level"] = ent_ref_level
        self.pane.sets["ref_level"] = var_ref_level
        self.pane.wgts["vbw"] = ent_vbw
        self.pane.sets["vbw"] = var_vbw
        self.pane.wgts["window"] = cb_window
        self.pane.sets["window"] = var_window

        ttk.Label(self.pane.settings, text="Scale/Div").grid(row=row, column=0)
        ent_scale.grid(row=row, column=1)
        row += 1
        ttk.Label(self.pane.settings, text="Ref Level").grid(row=row, column=0)
        ent_ref_level.grid(row=row, column=1)
        row += 1
        ttk.Label(self.pane.settings, text="VBW").grid(row=row, column=0)
        ent_vbw.grid(row=row, column=1)
        row += 1
        ttk.Label(self.pane.settings, text="Window").grid(row=row, column=0)
        cb_window.grid(row=row, column=1)
        row += 1
        return row

    # --- GUI bind events and setters --- #
    def handle_event(self, event):
        if event.widget == self.pane.wgts["scale"]:
            self.set_scale(self.pane.sets["scale"].get())
        elif event.widget == self.pane.wgts["ref_level"]:
            self.set_ref_level(self.pane.sets["ref_level"].get())
        elif event.widget == self.pane.wgts["vbw"]:
            self.set_vbw(self.pane.sets["vbw"].get())
        elif event.widget == self.pane.wgts["window"]:
            self.set_window(self.pane.sets["window"].get())

    def set_scale(self, scale):
        """set plot scale"""
        try:
            scale = float(scale)
            self.scale = scale
        except ValueError:
            scale = self.scale
        self.pane.sets["scale"].set(str(self.scale))

    def set_ref_level(self, ref):
        """Set plot ref level"""
        try:
            ref = float(ref)
            self.ref_level = ref
        except ValueError:
            ref = self.ref_level
        self.pane.sets["ref_level"].set(str(self.ref_level))

    def set_vbw(self, smooth):
        """Set plot vbw"""
        try:
            smooth = float(smooth)
            if smooth <= 0.0:
                smooth = 0.0
            self.vbw = smooth
        except ValueError:
            smooth = self.vbw
        self.pane.sets["vbw"].set(str(self.vbw))
    def set_window(self, window):
        """Set plot window function"""
        self.window = window
