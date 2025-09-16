"""Initialize pyspecan module/script"""
import importlib

from . import err
from .config import config, Mode, View
from .obj import Frequency

from .model.model import Model

class SpecAn:
    """Class to initialize pyspecan"""
    __slots__ = ("model", "view", "controller")
    def __init__(self, view, mode="psd", **kwargs):
        file = kwargs.get("file", config.SENTINEL)
        if file is not config.SENTINEL:
            del kwargs["file"]
        else:
            file = None
        fmt = kwargs.get("dtype", config.SENTINEL)
        if fmt is not config.SENTINEL:
            del kwargs["dtype"]
        else:
            fmt = "cf32"
        Fs = kwargs.get("Fs", config.SENTINEL)
        if Fs is not config.SENTINEL:
            del kwargs["Fs"]
        else:
            Fs = 1
        cf = kwargs.get("cf", config.SENTINEL)
        if cf is not config.SENTINEL:
            del kwargs["cf"]
        else:
            cf = 0
        nfft = kwargs.get("nfft", config.SENTINEL)
        if nfft is not config.SENTINEL:
            del kwargs["nfft"]
        else:
            nfft = 1024

        if config.PROFILE:
            from .utils.monitor import Profile
            Profile().enable()

        if config.MON_MEM:
            from .utils.monitor import Memory
            Memory().start()

        if not isinstance(mode, Mode):
            mode = Mode[mode]
            if mode == Mode.NONE:
                raise err.UnknownOption(f"Unknown mode {mode}")
        if not isinstance(view, View):
            view = View.get(view)
            if view == View.NONE:
                raise err.UnknownOption(f"Unknown view {view}")

        config.MODE = mode # set global mode

        Fs = Frequency.get(Fs)
        cf = Frequency.get(cf)

        self.model = Model(file, fmt, nfft, Fs, cf)

        v = importlib.import_module(f".view.{view.path}", "pyspecan").View
        self.view = v(**kwargs)

        ctrl = importlib.import_module(f".controller.{view.path}", "pyspecan").Controller
        self.controller = ctrl(self.model, self.view, **kwargs)

        self.model.show()
        self.view.mainloop()

        if config.MON_MEM:
            from .utils.monitor import Memory
            Memory().stop()

        if config.PROFILE:
            from .utils.monitor import Profile
            Profile().disable()
            if config.PROFILE_PATH is None:
                Profile().show()
            else:
                Profile().dump(config.PROFILE_PATH)
