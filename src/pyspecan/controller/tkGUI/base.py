"""Base Controllers for tkGUI Controller"""
import argparse

import tkinter as tk

import numpy as np

from ...utils.window import WindowLUT

from ...view.tkGUI.base import GUIPlot
# from ...view.tkGUI.base import GUIBlitPlot
from ...view.tkGUI.base import GUIFreqPlot

def define_args(parser: argparse.ArgumentParser):
    parser.add_argument("-rl", "--ref_level", default=0.0, help="ref Level")
    parser.add_argument("-sd", "--scale_div", default=10.0, help="scale per division")
    parser.add_argument("-vb", "--vbw", default=10.0, help="video bandwidth")
    parser.add_argument("-w", "--window", default="blackman", choices=[k for k in WindowLUT.keys()], help="FFT window function")

class _PlotController:
    """Controller for view.tkGUI.GUIPlot"""
    __slots__ = ("view",)
    def __init__(self, view: GUIPlot):
        self.view = view
        self.view.btn_toggle.configure(command=self.toggle_settings)

    def toggle_settings(self, *args, **kwargs):
        """Toggle settings panel visibility"""
        if self.view.fr_sets.winfo_ismapped():
            self.view.fr_sets.forget()
            # self.btn_toggle.config(text="Show Settings")
        else:
            self.view.fr_sets.pack(side=tk.LEFT, fill=tk.Y, before=self.view.fr_canv)
            # self.btn_toggle.config(text="Hide Settings")

    def update(self):
        """Update view plot"""
        self.view.plotter.update()

    def reset(self):
        """Reset plot view"""
        pass

    def plot(self, *args, **kwargs):
        """Update plot data"""
        raise NotImplementedError()

class FreqPlotController(_PlotController):
    """Controller for view.tkGUI.GUIFreqPlot"""
    __slots__ = ("window", "vbw", "scale", "ref_level")
    def __init__(self, view: GUIFreqPlot, **kwargs):
        super().__init__(view)
        self.view: GUIFreqPlot = self.view # type hint
        self.window =  kwargs.get("window", "blackman")
        self.vbw = kwargs.get("vbw", 10.0)
        self.scale = kwargs.get("scale_div", 10.0)
        self.ref_level = kwargs.get("ref_level", 0.0)

        self.view.settings["scale"].set(str(self.scale))
        self.view.wg_sets["scale"].bind("<Return>", self.handle_event)
        self.view.settings["ref_level"].set(str(self.ref_level))
        self.view.wg_sets["ref_level"].bind("<Return>", self.handle_event)
        self.view.settings["vbw"].set(str(self.vbw))
        self.view.wg_sets["vbw"].bind("<Return>", self.handle_event)
        self.view.settings["window"].set(self.window)
        self.view.wg_sets["window"].configure(values=[k for k in WindowLUT.keys()])
        self.view.wg_sets["window"].bind("<<ComboboxSelected>>", self.handle_event)
        self.set_ref_level(self.view.settings["ref_level"].get())

    def update(self):
        self.view.plotter.canvas.draw()

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
            self.view.lbl_lo.place(relx=0.2, rely=0.9, width=20, height=20)
        else:
            if self.view.lbl_lo.winfo_ismapped():
                self.view.lbl_lo.place_forget()
        if np.all(psd > self.y_top):
            self.view.lbl_hi.place(relx=0.2, rely=0.1, width=20, height=20)
        else:
            if self.view.lbl_hi.winfo_ismapped():
                self.view.lbl_hi.place_forget()

    # --- GUI bind events and setters --- #
    def handle_event(self, event):
        if event.widget == self.view.wg_sets["scale"]:
            self.set_scale(self.view.settings["scale"].get())
        elif event.widget == self.view.wg_sets["ref_level"]:
            self.set_ref_level(self.view.settings["ref_level"].get())
        elif event.widget == self.view.wg_sets["vbw"]:
            self.set_vbw(self.view.settings["vbw"].get())
        elif event.widget == self.view.wg_sets["window"]:
            self.set_window(self.view.settings["window"].get())

    def set_scale(self, scale):
        """set plot scale"""
        try:
            scale = float(scale)
            self.scale = scale
        except ValueError:
            scale = self.scale
        self.view.settings["scale"].set(str(self.scale))
    def set_ref_level(self, ref):
        """Set plot ref level"""
        try:
            ref = float(ref)
            self.ref_level = ref
        except ValueError:
            ref = self.ref_level
        self.view.settings["ref_level"].set(str(self.ref_level))
    def set_vbw(self, smooth):
        """Set plot vbw"""
        try:
            smooth = float(smooth)
            self.vbw = smooth
        except ValueError:
            smooth = self.vbw
        self.view.settings["vbw"].set(str(self.vbw))
    def set_window(self, window):
        """Set plot window function"""
        self.window = window
