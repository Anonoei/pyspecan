import numpy as np
import tkinter as tk

from .plot import GUIPlot, GUIBlitPlot

from ...utils import vbw

class PSD(GUIBlitPlot):
    def __init__(self, view, root):
        self._psd_min = None
        self._psd_max = None
        self._vbw = 10.0
        self._scale = 10.0
        self._ref_level = 0.0
        super().__init__(view, root)
        self._set_ref_level()

        self.lbl_lo = tk.Label(self.fr_canv, text="V")
        self.lbl_hi = tk.Label(self.fr_canv, text="^")

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

        var_psd_min = tk.IntVar(self.fr_sets, 1)
        chk_show_min = tk.Checkbutton(parent, onvalue=1, offvalue=0,
                variable=var_psd_min, command=self._toggle_psd_min)

        var_psd_max = tk.IntVar(self.fr_sets, 1)
        chk_show_max = tk.Checkbutton(parent, onvalue=1, offvalue=0,
                variable=var_psd_max, command=self._toggle_psd_max)

        self.wg_sets["scale"] = ent_scale
        self.settings["scale"] = var_scale
        self.wg_sets["ref_level"] = ent_ref_level
        self.settings["ref_level"] = var_ref_level
        self.wg_sets["vbw"] = ent_vbw
        self.settings["vbw"] = var_vbw
        self.wg_sets["show_min"] = chk_show_min
        self.settings["show_min"] = var_psd_min
        self.wg_sets["show_max"] = chk_show_max
        self.settings["show_max"] = var_psd_max

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
        tk.Label(parent, text="Max Hold").grid(row=row, column=0)
        chk_show_max.grid(row=row, column=1)
        row += 1
        tk.Label(parent, text="Min Hold").grid(row=row, column=0)
        chk_show_min.grid(row=row, column=1)

    def _set_scale(self, *args, **kwargs):
        scale = self.settings["scale"].get()
        try:
            scale = float(scale)
            self._scale = scale
            ref = float(self.settings["ref_level"].get())
            self._plot.set_ylim(0, ref - (10*scale), ref)
        except ValueError:
            scale = self._scale
        self.settings["scale"].set(str(self._scale))

    def _set_ref_level(self, *args, **kwargs):
        ref = self.settings["ref_level"].get()
        try:
            ref = float(ref)
            self._ref_level = ref
            scale = float(self.settings["scale"].get())
            self._plot.set_ylim(0, ref - (10*scale), ref)
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

    def _toggle_psd_min(self):
        if self.settings["show_max"].get() == 0:
            self._psd_max = None
        self.update()

    def _toggle_psd_max(self):
        if self.settings["show_min"].get() == 0:
            self._psd_min = None
        self.update()

    def plot(self, idx, *args, **kwargs):
        self._plot.ax(idx).set_autoscale_on(False)
        self._plot.ax(idx).locator_params(axis="x", nbins=5)
        self._plot.ax(idx).locator_params(axis="y", nbins=10)
        self._plot.ax(idx).grid(True, alpha=0.2)
        self._plot.ax(idx).set_title("PSD")
        freq, psd = args[0:2]
        psd = vbw.vbw(psd, self._vbw)
        if self.settings["show_max"].get() == 1:
            if self._psd_max is None:
                self._psd_max = np.repeat(-np.inf, len(psd))
            self._psd_max[psd > self._psd_max] = psd[psd > self._psd_max]
            line_max = super().plot(idx, freq, self._psd_max, name="psd_max", color="r")
        else:
            line_max = None
        if self.settings["show_min"].get() == 1:
            if self._psd_min is None:
                self._psd_min = np.repeat(np.inf, len(psd))
            self._psd_min[psd < self._psd_min] = psd[psd < self._psd_min]
            line_min = super().plot(idx, freq, self._psd_min, name="psd_min", color="b")
        else:
            line_min = None
        line_psd = super().plot(idx, freq, psd, name="psd", color="y")
        if not self._plot.ax(idx).get_xlim() == (freq[0], freq[-1]):
            self._plot.set_xlim(idx, freq[0], freq[-1])
        if np.all(psd < (self._ref_level - (10*self._scale))):
            self.lbl_lo.place(relx=0.2, rely=0.9, width=20, height=20)
        else:
            if self.lbl_lo.winfo_ismapped():
                self.lbl_lo.place_forget()
        if np.all(psd > self._ref_level):
            self.lbl_hi.place(relx=0.2, rely=0.1, width=20, height=20)
        else:
            if self.lbl_hi.winfo_ismapped():
                self.lbl_hi.place_forget()
        return (line_psd, line_max, line_min)

    def reset(self):
        self._psd_min = None
        self._psd_max = None
