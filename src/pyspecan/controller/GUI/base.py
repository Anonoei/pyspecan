import tkinter as tk

from ...utils.window import WindowLUT

from ...view.GUI.base import GUIPlot, GUIBlitPlot, GUIFreqPlot

class PlotController:
    __slots__ = ("view",)
    def __init__(self, view: GUIPlot):
        self.view = view
        self.view.btn_toggle.configure(command=self.toggle_settings)

    def toggle_settings(self, *args, **kwargs):
        if self.view.fr_sets.winfo_ismapped():
            self.view.fr_sets.forget()
            # self.btn_toggle.config(text="Show Settings")
        else:
            self.view.fr_sets.pack(side=tk.LEFT, fill=tk.Y, before=self.view.fr_canv)
            # self.btn_toggle.config(text="Hide Settings")

    def update(self):
        self.view.plotter.update()

class FreqPlotController(PlotController):
    __slots__ = ("window", "vbw", "scale", "ref_level")
    def __init__(self, view: GUIFreqPlot, vbw=10.0, scale=10.0, ref_level=0.0):
        super().__init__(view)
        self.view: GUIFreqPlot = self.view # type hint
        self.window = "blackman"
        self.vbw = vbw
        self.scale = scale
        self.ref_level = ref_level

        self.view.settings["scale"].set(str(self.scale))
        self.view.wg_sets["scale"].bind("<Return>", self.set_scale)
        self.view.settings["ref_level"].set(str(self.ref_level))
        self.view.wg_sets["ref_level"].bind("<Return>", self.set_ref_level)
        self.view.settings["vbw"].set(str(self.vbw))
        self.view.wg_sets["vbw"].bind("<Return>", self.set_vbw)
        self.view.settings["window"].set(self.window)
        self.view.wg_sets["window"].configure(values=[k for k in WindowLUT.keys()])
        self.view.wg_sets["window"].bind("<<ComboboxSelected>>", self.set_window)
        self.set_ref_level()

    @property
    def y_top(self):
        return self.ref_level
    @property
    def y_btm(self):
        return self.ref_level - (10*self.scale)

    def set_scale(self, *args, **kwargs):
        scale = self.view.settings["scale"].get()
        try:
            scale = float(scale)
            self.scale = scale
        except ValueError:
            scale = self.scale
        self.view.settings["scale"].set(str(self.scale))

    def set_ref_level(self, *args, **kwargs):
        ref = self.view.settings["ref_level"].get()
        try:
            ref = float(ref)
            self.ref_level = ref
        except ValueError:
            ref = self.ref_level
        self.view.settings["ref_level"].set(str(self.ref_level))

    def set_vbw(self, *args, **kwargs):
        smooth = self.view.settings["vbw"].get()
        try:
            smooth = float(smooth)
            self.vbw = smooth
        except ValueError:
            smooth = self.vbw
        self.view.settings["vbw"].set(str(self.vbw))

    def set_window(self, *args, **kwargs):
        self.window = self.view.settings["window"].get()
