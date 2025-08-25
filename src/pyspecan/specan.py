import tkinter as tk

from .model.model import Model

from . import err
from .utils import dialog

class SpecAn:
    __slots__ = ("model", "view", "controller")
    def __init__(self, ui, mode="psd", path=None, fmt=None, nfft=1024, Fs=1, cf=0):
        if not mode in ("psd", "rt"):
            raise err.UnknownOption(f"Unknown mode {mode}")
        self.model = Model(mode, path, fmt, nfft, Fs, cf)

        if ui in ("c", "cui", "CUI"):
            from .view.cui import CUI
            tk.Tk().withdraw()
            self.view = CUI(mode, self)
            from .controller.cui import Controller
            self.controller = Controller(self.model, self.view)
        elif ui in("g", "gui", "GUI"):
            from .view.gui import GUI
            self.view = GUI(mode, self)
            from .controller.gui import Controller
            self.controller = Controller(self.model, self.view)
        else:
            raise err.UnknownOption(f"Unknown UI {ui}")

        self.model.show()
        self.view.mainloop()
