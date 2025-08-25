import numpy as np
import tkinter as tk
from tkinter import ttk

from .plot import GUIPlot, GUIBlitPlot

from ...utils import vbw
from ...utils.window import WindowLUT
from ...utils import matrix
from ...plot.color import cmap

class Persistent(GUIBlitPlot):
    def __init__(self, view, root):
        self._window = "blackman"
        self._vbw = 10.0
        self._scale = 10.0
        self._ref_level = 0.0
        self._x = 1001
        self._y = 600
        self._cmap = "hot"
        super().__init__(view, root)
        self._set_ref_level()

        self.lbl_lo = tk.Label(self.fr_canv, text="V")
        self.lbl_hi = tk.Label(self.fr_canv, text="^")

        # self._plot.set_ylim(0, 0, self._y)
        # self._plot.set_xlim(0, 0, self._x)

        self._set_x()
        self._set_y()

    @property
    def vbw(self):
        return self._vbw

    @property
    def window(self):
        return self._window

    def draw_settings(self, parent):
        var_scale = tk.StringVar(self.fr_sets, str(self._scale))
        ent_scale = tk.Entry(self.fr_sets, textvariable=var_scale, width=10)
        ent_scale.bind("<Return>", self._set_scale)

        var_ref_level = tk.StringVar(self.fr_sets, str(self._ref_level))
        ent_ref_level = tk.Entry(self.fr_sets, textvariable=var_ref_level, width=10)
        ent_ref_level.bind("<Return>", self._set_ref_level)

        var_vbw = tk.StringVar(self.fr_sets, str(self._vbw))
        ent_vbw = tk.Entry(self.fr_sets, textvariable=var_vbw, width=10)
        ent_vbw.bind("<Return>", self._set_vbw)

        var_window = tk.StringVar(self.fr_sets, self._window)
        cb_window = ttk.Combobox(self.fr_sets, textvariable=var_window, width=9, values=[k for k in WindowLUT.keys()])
        cb_window.bind("<<ComboboxSelected>>", self._set_window)

        var_cmap = tk.StringVar(self.fr_sets, self._cmap)
        cb_cmap = ttk.Combobox(self.fr_sets, textvariable=var_cmap, width=9, values=[k for k in cmap.keys()])
        cb_cmap.bind("<<ComboboxSelected>>", self._set_cmap)

        self.wg_sets["scale"] = ent_scale
        self.settings["scale"] = var_scale
        self.wg_sets["ref_level"] = ent_ref_level
        self.settings["ref_level"] = var_ref_level
        self.wg_sets["vbw"] = ent_vbw
        self.settings["vbw"] = var_vbw
        self.wg_sets["window"] = cb_window
        self.settings["window"] = var_window
        self.wg_sets["cmap"] = cb_cmap
        self.settings["cmap"] = var_cmap

        row = 0
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
        tk.Label(parent, text="Colors").grid(row=row, column=0)
        cb_cmap.grid(row=row, column=1)

    def _set_y(self):
        y_mul = [0.0,0.2,0.4,0.6,0.8,1.0]
        y_max = self._ref_level
        y_min = self._ref_level - (10*self._scale)
        y_rng = abs(abs(y_max) - abs(y_min))
        y_off = y_min if y_min < 0 else -y_min

        y_tick = [self._y*m for m in y_mul]
        y_text = [f"{(y_rng*m)+y_off:.1f}" for m in y_mul]
        self._plot.ax(0).set_yticks(y_tick, y_text)
        self._plot.relim(0)

    def _set_x(self):
        x_mul = [0.0,0.25,0.5,0.75,1.0]

        x_tick = [self._x*m for m in x_mul]
        x_text = [f"{m-self._x/2:.1f}" for m in x_tick]
        self._plot.ax(0).set_xticks(x_tick, x_text)
        self._plot.relim(0)

    def _set_scale(self, *args, **kwargs):
        scale = self.settings["scale"].get()
        try:
            scale = float(scale)
            self._scale = scale
            self._set_y()
        except ValueError:
            scale = self._scale
        self.settings["scale"].set(str(self._scale))

    def _set_ref_level(self, *args, **kwargs):
        ref = self.settings["ref_level"].get()
        try:
            ref = float(ref)
            self._ref_level = ref
            self._set_y()
        except ValueError:
            ref = self._ref_level
        self.settings["ref_level"].set(str(self._ref_level))

    def _set_vbw(self, *args, **kwargs):
        smooth = self.settings["vbw"].get()
        try:
            smooth = float(smooth)
            if not self._vbw == smooth:
                self._vbw = smooth
                self._psd_max = None
                self._psd_min = None
        except ValueError:
            smooth = self._vbw
        self.settings["vbw"].set(str(self._vbw))
        return smooth

    def _set_window(self, *args, **kwargs):
        self._window = self.settings["window"].get()

    def _set_cmap(self, *args, **kwargs):
        self._cmap = self.settings["cmap"].get()

    def plot(self, idx, *args, **kwargs):
        self._plot.ax(idx).set_autoscale_on(False)
        self._plot.ax(idx).locator_params(axis="x", nbins=5)
        self._plot.ax(idx).locator_params(axis="y", nbins=10)
        self._plot.ax(idx).grid(True, alpha=0.2)
        self._plot.ax(idx).set_title("Persistent")
        freq, psds = args[0:2]
        mat = matrix.cvec(self._x, self._y, psds, self._ref_level, self._ref_level-(10*self._scale))
        mat = mat / np.max(mat)

        im = self._plot.imshow(
                idx, mat, name="mat", cmap=cmap[self._cmap],
                vmin=0, vmax=1,
                aspect="auto",
                interpolation="nearest", resample=False,
                rasterized=True)

        # if not self._plot.ax(idx).get_xlim() == (freq[0], freq[-1]):
        #     self._plot.set_xlim(idx, freq[0], freq[-1])
        if np.all(psds < (self._ref_level - (10*self._scale))):
            self.lbl_lo.place(relx=0.2, rely=0.9, width=20, height=20)
        else:
            if self.lbl_lo.winfo_ismapped():
                self.lbl_lo.place_forget()
        if np.all(psds > self._ref_level):
            self.lbl_hi.place(relx=0.2, rely=0.1, width=20, height=20)
        else:
            if self.lbl_hi.winfo_ismapped():
                self.lbl_hi.place_forget()
        return im
