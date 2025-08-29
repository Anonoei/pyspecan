"""Initialize pyspecan module/script"""
import importlib

from . import err
from .config import config, Mode, View
from .model.model import Model

class SpecAn:
    """Class to initialize pyspecan"""
    __slots__ = ("model", "view", "controller")
    def __init__(self, view, mode="psd", path=None, fmt=None, nfft=1024, Fs=1, cf=0):
        if not isinstance(mode, Mode):
            if not mode in Mode.choices():
                raise err.UnknownOption(f"Unknown mode {mode}")
            mode = Mode[mode]
        if not isinstance(view, View):
            if not view in View.choices():
                raise err.UnknownOption(f"Unknown view {view}")
            view = View.get_view(view)

        config.MODE = mode # set global mode

        self.model = Model(path, fmt, nfft, Fs, cf)

        v = importlib.import_module(f".view.{view.path}", "pyspecan").View
        self.view = v(self)

        ctrl = importlib.import_module(f".controller.{view.path}", "pyspecan").Controller
        self.controller = ctrl(self.model, self.view)

        self.model.show()
        self.view.mainloop()
