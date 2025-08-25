import numpy as np
import tkinter as tk
from tkinter import ttk

from .base import FreqPlotController
from ....view.GUI.plot import PSD as viewPSD

from ....utils import vbw

class PSD(FreqPlotController):
    __slots__ = ("psd_min", "psd_max")
    def __init__(self, view):
        super().__init__(view)
        # self.view: viewPSD = self.view # type hint
        self.psd_min = None
        self.psd_max = None

        self.view.settings["show_min"].set(1)
        self.view.wg_sets["show_min"].configure(command=self.toggle_psd_min)
        self.view.settings["show_max"].set(1)
        self.view.wg_sets["show_max"].configure(command=self.toggle_psd_max)

        self.view.plotter.ax(0).set_autoscale_on(False)
        self.view.plotter.ax(0).locator_params(axis="x", nbins=5)
        self.view.plotter.ax(0).locator_params(axis="y", nbins=10)
        self.view.plotter.ax(0).grid(True, alpha=0.2)

    def reset(self):
        self.psd_min = None
        self.psd_max = None

    def set_vbw(self, *args, **kwargs):
        prev = self.vbw
        super().set_vbw(*args, **kwargs)
        if not prev == self.vbw:
            self.reset()

    def toggle_psd_min(self):
        if self.view.settings["show_max"].get() == 0:
            self.psd_max = None
        self.update()

    def toggle_psd_max(self):
        if self.view.settings["show_min"].get() == 0:
            self.psd_min = None
        self.update()

    def plot(self, idx, freq, psd):
        self.view.plotter.ax(idx).set_title("PSD")
        psd = vbw.vbw(psd, self.vbw)
        if self.view.settings["show_max"].get() == 1:
            if self.psd_max is None:
                self.psd_max = np.repeat(-np.inf, len(psd))
            self.psd_max[psd > self.psd_max] = psd[psd > self.psd_max]
            line_max = self.view.plot(idx, freq, self.psd_max, name="psd_max", color="r")
        else:
            line_max = None
        if self.view.settings["show_min"].get() == 1:
            if self.psd_min is None:
                self.psd_min = np.repeat(np.inf, len(psd))
            self.psd_min[psd < self.psd_min] = psd[psd < self.psd_min]
            line_min = self.view.plot(idx, freq, self.psd_min, name="psd_min", color="b")
        else:
            line_min = None
        line_psd = self.view.plot(idx, freq, psd, name="psd", color="y")

        if not self.view.plotter.ax(idx).get_xlim() == (freq[0], freq[-1]):
            self.view.plotter.set_xlim(idx, freq[0], freq[-1])
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
        return (line_psd, line_max, line_min)
