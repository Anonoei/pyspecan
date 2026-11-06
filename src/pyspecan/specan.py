"""Initialize pyspecan module/script"""
from . import err
from .config import config, Sink, View

from .model.model import Model, GetModel
from .view.view import GetView
from .controller.controller import GetController

class SpecAn:
    """Class to initialize pyspecan"""
    __slots__ = ("model", "view", "controller")
    def __init__(self, view, sink="file", **kwargs):
        if config.PROFILE:
            from .utils.monitor import Profile
            Profile().enable()

        if config.MON_MEM:
            from .utils.monitor import Memory
            Memory().start()

        if not isinstance(sink, Sink):
            sink = Sink[sink]
            if sink == Sink.NONE:
                raise err.UnknownOption(f"Unknown sink {sink}")
        if not isinstance(view, View):
            view = View.get(view)
            if view == View.NONE:
                raise err.UnknownOption(f"Unknown view {view}")

        self.model: Model = GetModel(sink)(**kwargs)

        self.view = GetView(view, sink)(**kwargs)
        self.controller = GetController(view, sink)(self.model, self.view, **kwargs)

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
