"""Plot base class and registry

A plot turns the shared `Source` into a `Frame`. It never touches a toolkit.
Subclasses declare `SETTINGS`, implement `render()` and register with `@plot("Name")`.
"""
from ..utils.registry import Registry
from .frame import Frame, LINE
from .settings import Setting

PLOTS: Registry = Registry("plot")

def plot(name: str):
    """Register a plot class under `name`, the name views show in their plot picker"""
    def deco(cls):
        cls.NAME = name
        return PLOTS.register(name)(cls)
    return deco

def available(features) -> list[str]:
    """Names of the plots a view that can draw `features` is able to show"""
    return [name for name, cls in PLOTS.items() if cls.FEATURES <= set(features)]

class Plot:
    NAME = ""
    TITLE = ""
    SETTINGS: tuple[Setting, ...] = ()
    FEATURES: frozenset = frozenset({LINE}) # drawing features the frames need, see plots.frame

    def __init__(self, source, **kwargs):
        """`kwargs` may carry initial values for any of this plot's settings, others are ignored"""
        self.source = source
        self.enabled = True # False -> paused
        self._cfg = {}
        for s in self.SETTINGS:
            try:
                self._cfg[s.key] = s.parse(kwargs.get(s.key, s.default))
            except ValueError:
                if s.key not in kwargs:
                    raise
                self._cfg[s.key] = s.parse(s.default) # a bad launch argument falls back to the default
        self.reset()

    def __getattr__(self, name):
        # only reached when normal lookup fails: settings read as attributes
        cfg = self.__dict__.get("_cfg", {})
        if name in cfg:
            return cfg[name]
        raise AttributeError(name)

    # --- settings --- #
    def fields(self) -> list[dict]:
        """Description of the editable settings, for building a view's widgets"""
        return [s.to_dict() for s in self.SETTINGS]

    def settings(self) -> dict:
        return {"enabled": self.enabled, **self._cfg}

    def set(self, key, value):
        """Change a setting (or `enabled`), raises ValueError if it is unknown or invalid"""
        if key == "enabled":
            self.enabled = bool(value)
            return
        for s in self.SETTINGS:
            if s.key == key:
                self._cfg[key] = s.parse(value)
                self.changed(key)
                if s.reset:
                    self.reset()
                return
        raise ValueError(f"unknown plot setting {key!r}")

    def changed(self, key):
        """A setting changed, called before the reset it may trigger"""

    # --- compute --- #
    def reset(self):
        """Drop accumulated state (holds, history)"""

    def update(self) -> Frame | None:
        """Frame for the source's current block, None while paused or without data"""
        if not self.enabled:
            return None
        return self.render()

    def render(self) -> Frame | None:
        raise NotImplementedError()
