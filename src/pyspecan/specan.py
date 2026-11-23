"""Initialize pyspecan module/script"""
from . import err
from .arguments import split
from .config import Sink, View, config
from .controller.controller import GetController
from .model.model import GetModel, Model
from .plots import layout_from_kwargs
from .view.view import GetView


class SpecAn:
    """Run pyspecan: `SpecAn("web", "file", path="x.cf32", Fs="250k", layout=...)`

    `kwargs` are the command line options by dest (`python -m pyspecan -v <view> -s <sink> -h` lists
    them), each part gets only its own. `layout`: a plots.LayoutSpec or a json layout file path"""
    __slots__ = ("model", "view", "controller")
    def __init__(self, view="tk", sink="file", layout=None, **kwargs):
        if config.PROFILE:
            from .utils.monitor import Profile
            Profile().enable()

        if config.MON_MEM:
            from .utils.monitor import Memory
            Memory().start()

        v, s = View.get(view), Sink.get(sink)
        if v == View.NONE:
            raise err.UnknownOption(f"Unknown view {view}")
        if s == Sink.NONE:
            raise err.UnknownOption(f"Unknown sink {sink}")

        part = split(v, s, kwargs)
        spec = layout_from_kwargs({**part["plots"], "layout": layout}) # bad layouts fail before anything opens

        self.model: Model = GetModel(s)(**part["model"])
        self.view = GetView(v, s)(**part["ui"])
        self.controller = GetController(v, s)(self.model, self.view, layout=spec, **part["ui"])

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
