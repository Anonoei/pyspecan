"""Plot base class and registry

A plot turns the shared `Source` into a `Frame`. It never touches a toolkit.
Subclasses declare `SETTINGS`, implement `render()` and register with `@plot("Name")`.
"""
from dataclasses import dataclass

from ..utils.registry import Registry
from .frame import LINE, Frame
from .settings import GLOBAL_SETTINGS, Setting, by_key


def default_globals(**kwargs) -> dict:
    """Values of the GLOBAL_SETTINGS, from `kwargs` where given"""
    return {s.key: s.parse(kwargs.get(s.key, s.default)) for s in GLOBAL_SETTINGS}

PLOTS: Registry = Registry("plot")

# what views group the plot picker by, in this order (a plot that names none is "Other")
CATEGORIES = ("Spectrum", "Time-frequency", "Time domain", "Measurements", "Analog demodulation", "Digital demodulation",
              "Modulation quality", "Channel and signal analysis", "Decoding", "Other")

@dataclass(frozen=True)
class About:
    """What views tell about a plot (the picker's tooltip)

    data: the input and what is done to it. shows: what is on the axes, what each trace or color means.
    use: things to use it for. cost: rendering a block costs about this many PSDs (dev/benchmark.py at its defaults:
    1 MS/s, 1024 point FFT, 50 ms blocks), None to say nothing"""
    data: str
    shows: str
    use: tuple[str, ...] = ()
    cost: float | None = None

def about_text(name: str, a: dict) -> str:
    """What a plot does as plain text (a tooltip, the console's about): its category, Data, Shows, Use, Cost.
    `a` is Plot.about()"""
    lines = [f"{name} ({a['category']})"]
    if a["data"]:
        lines.append(f"Data: {a['data']}")
    if a["shows"]:
        lines.append(f"Shows: {a['shows']}")
    if a["use"]:
        lines += ["Use:", *[f"  • {u}" for u in a["use"]]]
    if a["cost"]:
        lines.append(f"Cost: {a['cost']}")
    return "\n".join(lines)

def cost_text(cost: float | None) -> str:
    """light / medium / heavy, and the number"""
    if cost is None:
        return ""
    tier = "light" if cost < 2 else "medium" if cost < 10 else "heavy"
    num = f"{cost:.2g}" if cost < 10 else f"{cost:.0f}"
    return f"{tier}, about {num}x a PSD"

# every plot has it (added when it registers): heavy plots can skip blocks so the rest of a layout keeps up
SETTING_EVERY = Setting("every", "Update every", "int", default=1, min=1, max=1000, hint="blocks", group="Display",
                        help="render every Nth block only (the ones between are skipped, not computed): a heavy plot "
                             "keeps the rest of the layout live")

def plot(name: str):
    """Register a plot class under `name`, the name views show in their plot picker. Adds the "Update every"
    setting every plot has"""
    def deco(cls):
        cls.NAME = name
        if by_key(cls.SETTINGS, SETTING_EVERY.key) is None:
            cls.SETTINGS = tuple(cls.SETTINGS) + (SETTING_EVERY,)
        return PLOTS.register(name)(cls)
    return deco

def available(features, radio: bool = True) -> list[str]:
    """Names of the plots a view that can draw `features` is able to show; `radio`: the source is a radio this program
    can tune (plots that retune it, NEEDS_RADIO, are left out otherwise)"""
    return [name for name, cls in PLOTS.items() if cls.FEATURES <= set(features) and (radio or not cls.NEEDS_RADIO)]

class Plot:
    """Settings resolve through a hierarchy: global (`globals`, shared by every plot) -> link group
    (`link.values`, for "link" scope settings while the plot is linked) -> the plot's own values"""
    NAME = ""
    TITLE = ""
    NEEDS_RADIO = False # it tunes a live radio itself (a sweep): not offered for files
    SETTINGS: tuple[Setting, ...] = ()
    FEATURES: frozenset = frozenset({LINE}) # drawing features the frames need, see plots.frame
    MARKERS = False                         # carries a `markers` set the user can add markers and measurements to
    LINK_DOMAIN: str | None = None          # plots of the same domain can be linked to share their "link" settings
    ACTIONS: tuple[str, ...] = ()           # what `act` does (store a reference trace), views offer them as buttons
    CATEGORY = "Other"                      # one of CATEGORIES, groups it in the plot picker
    ABOUT: About | None = None              # what views tell about it, see About

    def __init__(self, source, globals: dict | None = None, **kwargs):
        """`kwargs` may carry initial values for any of this plot's settings, others are ignored, bad ones raise ValueError.
        `globals` is the dict of global values shared with the other plots (built from `kwargs` when not given)"""
        self.source = source
        self.enabled = True # False -> paused
        self.link = None    # plotset.Link while linked
        self.globals = globals if globals is not None else default_globals(**kwargs)
        self._scope = {s.key: s.scope for s in self.SETTINGS}
        self._cfg = {}
        kwargs = self.migrate(kwargs)
        for s in self.SETTINGS:
            self._cfg[s.key] = s.parse(kwargs.get(s.key, s.default)) # raises on a bad value
        self.reset()

    @classmethod
    def about(cls) -> dict:
        """json-serializable description for views: category, data, shows, use, cost (text, "" when not given). A
        plot without ABOUT shows its docstring"""
        a = cls.ABOUT
        doc = " ".join((cls.__doc__ or "").split())
        category = cls.CATEGORY if cls.CATEGORY in CATEGORIES else "Other"
        if a is None:
            return {"category": category, "data": "", "shows": doc, "use": [], "cost": ""}
        return {"category": category, "data": a.data, "shows": a.shows, "use": list(a.use), "cost": cost_text(a.cost)}

    def __getattr__(self, name):
        # only reached when normal lookup fails: settings read as attributes
        d = self.__dict__
        link = d.get("link")
        if link is not None and d.get("_scope", {}).get(name) == "link" and name in link.values:
            return link.values[name]
        cfg = d.get("_cfg", {})
        if name in cfg:
            return cfg[name]
        g = d.get("globals")
        if g is not None and name in g:
            return g[name]
        raise AttributeError(name)

    # --- settings --- #
    @classmethod
    def migrate(cls, settings: dict) -> dict:
        """`settings` with the keys of an older version of the plot turned into today's (a layout saved back then
        still loads). Returns a new dict, the default changes nothing"""
        return settings

    def setting(self, key: str) -> Setting | None:
        """The descriptor of one of this plot's settings or a global one"""
        return by_key(self.SETTINGS, key) or by_key(GLOBAL_SETTINGS, key)

    def store(self, s: Setting) -> dict:
        """Where the value of `s` lives for this plot"""
        if s.scope == "global":
            return self.globals
        if s.scope == "link" and self.link is not None:
            return self.link.values
        return self._cfg

    def own_values(self) -> dict:
        """This plot's own and link values, without the globals"""
        return {s.key: getattr(self, s.key) for s in self.SETTINGS}

    def fields(self) -> list[dict]:
        """Description of the editable settings, for building a view's widgets"""
        return [s.to_dict() for s in self.SETTINGS]

    def settings(self) -> dict:
        return {"enabled": self.enabled, **self.own_values()}

    def set(self, key, value):
        """Change a setting (or `enabled`), raises ValueError if it is unknown or invalid.
        Only this plot hears of the change, `PlotSet.set` tells every plot sharing the value"""
        if key == "enabled":
            self.enabled = bool(value)
            return
        s = self.setting(key)
        if s is None:
            raise ValueError(f"unknown plot setting {key!r}")
        self.store(s)[key] = s.parse(value)
        self.apply(s)

    def apply(self, s: Setting):
        """React to a changed value of `s`"""
        self.changed(s.key)
        if s.reset:
            self.reset()

    def changed(self, key):
        """A setting changed, called before the reset it may trigger"""

    def act(self, action: str):
        """Do one of ACTIONS (on the latest data), raises ValueError for anything else"""
        raise ValueError(f"{self.NAME} has no action {action!r}, it has: {', '.join(self.ACTIONS) or 'none'}")

    # --- compute --- #
    def reset(self):
        """Drop accumulated state (holds, history)"""

    def update(self) -> Frame | None:
        """Frame for the source's current block, None while paused, without data, or on a block "Update every" skips.
        The same block again (a redraw after a change while stopped) always renders"""
        if not self.enabled:
            return None
        every = self._cfg.get("every", 1)
        if every > 1:
            seq = (getattr(self.source, "epoch", 0), getattr(self.source, "seq", 0))
            if seq != self.__dict__.get("_seen"): # a new block: counted once, skipped unless it is the Nth
                self._seen = seq
                count = self.__dict__.get("_blocks", 0)
                self._blocks = count + 1
                if count % every:
                    return None
            # the same block again is a redraw after a change: it renders, skipped or not
        return self.render()

    def render(self) -> Frame | None:
        raise NotImplementedError()
