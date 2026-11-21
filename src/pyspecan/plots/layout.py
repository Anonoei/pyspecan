"""Launch layouts: which plots, in which rows, with which settings, links and markers

A `LayoutSpec` is what a view starts with, and what it saves. It comes from the command line

    --plot "PSD vbw=5 unit=dBm link=a marker=peak" --plot "Spectrogram link=a" --row --plot persistence

or from a json file (`--layout`), and `PlotSet.apply` / `PlotSet.to_spec` turn it into plots and back:

    {"globals": {"cal_db": -10},
     "rows": [
       [{"type": "PSD", "link": "a", "settings": {"vbw": 5}, "markers": [{"kind": "peak"}]},
        {"type": "Spectrogram", "link": "a"}],
       [{"type": "Persistence", "settings": {"show_max": true}}]]}
"""
import json
import pathlib
import shlex
from dataclasses import dataclass, field

from .base import PLOTS
from .settings import ANALYSIS_SETTINGS, GLOBAL_SETTINGS, HAVE_RPPS, by_key


@dataclass
class PlotSpec:
    type: str
    settings: dict = field(default_factory=dict)
    link: str | None = None
    markers: list[dict] = field(default_factory=list) # {"kind": name, **params}

@dataclass
class LayoutSpec:
    rows: list[list[PlotSpec]] = field(default_factory=list)
    globals: dict = field(default_factory=dict)

    def plots(self):
        """(row, col, PlotSpec) of every plot"""
        for r, row in enumerate(self.rows):
            for c, p in enumerate(row):
                yield r, c, p

def default() -> LayoutSpec:
    return LayoutSpec([[PlotSpec("PSD")]])

EXT_HINT = "plots and marker kinds from extensions need their package installed, the DSP ones pyspecan[dsp] (rpps)"

def _norm(name: str) -> str:
    return "".join(ch for ch in str(name).lower() if ch.isalnum())

def resolve_type(name: str) -> str:
    """The registered plot name for `name`, ignoring case, spaces and underscores ("power_vs_time")"""
    want = _norm(name)
    for registered in PLOTS.names():
        if _norm(registered) == want:
            return registered
    raise ValueError(f"unknown plot {name!r}, choose from: {', '.join(PLOTS.names())} ({EXT_HINT})")

# --- command line --- #
def _marker(text: str) -> dict:
    """`kind` or `kind:key=value,key=value`"""
    kind, _, rest = text.partition(":")
    out = {"kind": kind.strip()}
    for item in filter(None, (p.strip() for p in rest.split(","))):
        k, sep, v = item.partition("=")
        if not sep:
            raise ValueError(f"marker setting {item!r} must look like key=value")
        out[k.strip()] = v.strip()
    return out

def parse_plot(text: str) -> PlotSpec:
    """One --plot value: the plot name, then key=value settings. `link=` and `marker=` are reserved"""
    name, settings, link, markers = [], {}, None, []
    for tok in shlex.split(text):
        key, sep, value = tok.partition("=")
        if not sep:
            if settings or link or markers:
                raise ValueError(f"{text!r}: the plot name has to come before its settings")
            name.append(tok)
        elif key == "link":
            link = value
        elif key == "marker":
            markers.append(_marker(value))
        else:
            settings[key] = value
    if not name:
        raise ValueError(f"{text!r}: no plot name")
    return PlotSpec(resolve_type(" ".join(name)), settings, link or None, markers)

def parse_inline(items: list[str | None], globals: dict | None = None) -> LayoutSpec:
    """The --plot values in order, None where --row started a new row"""
    rows: list[list[PlotSpec]] = [[]]
    for item in items:
        if item is None:
            if rows[-1]:
                rows.append([])
        else:
            rows[-1].append(parse_plot(item))
    return LayoutSpec([r for r in rows if r], dict(globals or {}))

# --- json --- #
_TOP_KEYS = {"rows", "globals"}
_PLOT_KEYS = {"type", "settings", "link", "markers"}

def from_dict(d: dict) -> LayoutSpec:
    if not isinstance(d, dict):
        raise ValueError("a layout is a json object with \"rows\"")
    if extra := set(d) - _TOP_KEYS:
        raise ValueError(f"unknown layout key(s): {', '.join(sorted(extra))}")
    rows = []
    for r, row in enumerate(d.get("rows", [])):
        if not isinstance(row, list):
            raise ValueError(f"row {r + 1}: a row is a list of plots")
        out = []
        for c, p in enumerate(row):
            where = f"row {r + 1}, plot {c + 1}"
            if not isinstance(p, dict) or "type" not in p:
                raise ValueError(f"{where}: a plot is an object with a \"type\"")
            if extra := set(p) - _PLOT_KEYS:
                raise ValueError(f"{where}: unknown key(s) {', '.join(sorted(extra))}")
            markers = p.get("markers", [])
            if not all(isinstance(m, dict) and "kind" in m for m in markers):
                raise ValueError(f"{where}: a marker is an object with a \"kind\"")
            out.append(PlotSpec(resolve_type(p["type"]), dict(p.get("settings", {})), p.get("link") or None,
                                [dict(m) for m in markers]))
        rows.append(out)
    return LayoutSpec(rows, _known_globals(dict(d.get("globals", {}))))

def _known_globals(globals: dict) -> dict:
    """A layout's globals without the analysis settings when rpps is missing: saved where it was installed, they
    have nothing to set here (the DSP plots themselves still fail, naming what to install)"""
    if HAVE_RPPS:
        return globals
    dsp = {s.key for s in ANALYSIS_SETTINGS}
    return {k: v for k, v in globals.items() if k not in dsp}

def to_dict(spec: LayoutSpec) -> dict:
    d: dict = {}
    if spec.globals:
        d["globals"] = dict(spec.globals)
    d["rows"] = []
    for row in spec.rows:
        out = []
        for p in row:
            item: dict = {"type": p.type}
            if p.link:
                item["link"] = p.link
            if p.settings:
                item["settings"] = dict(p.settings)
            if p.markers:
                item["markers"] = [dict(m) for m in p.markers]
            out.append(item)
        d["rows"].append(out)
    return d

def loads(text: str) -> LayoutSpec:
    try:
        return from_dict(json.loads(text))
    except json.JSONDecodeError as e:
        raise ValueError(f"layout is not valid json: {e}") from None

def load(path) -> LayoutSpec:
    return loads(pathlib.Path(path).read_text())

def dumps(spec: LayoutSpec) -> str:
    return json.dumps(to_dict(spec), indent=2)

# --- checks --- #
def validate(spec: LayoutSpec, plot_types=None):
    """Raise ValueError naming the first thing in `spec` that can not be built.
    `plot_types`: the plot names the view can draw (all when None)"""
    from .markers import MARKER_KINDS
    if not spec.rows:
        raise ValueError("the layout has no plots")
    for key, value in spec.globals.items():
        s = by_key(GLOBAL_SETTINGS, key)
        if s is None:
            raise ValueError(f"unknown global setting {key!r}, choose from: {', '.join(g.key for g in GLOBAL_SETTINGS)}")
        s.parse(value)
    domains: dict[str, tuple[str, str]] = {} # link name -> (domain, first member)
    for r, c, p in spec.plots():
        where = f"row {r + 1}, plot {c + 1} ({p.type})"
        try:
            cls = PLOTS.get(p.type)
            if plot_types is not None and p.type not in plot_types:
                raise ValueError("this view can not draw it")
            for key, value in p.settings.items():
                s = by_key(cls.SETTINGS, key)
                if s is None:
                    if by_key(GLOBAL_SETTINGS, key) is not None:
                        raise ValueError(f"{key} is shared by every plot, give it under \"globals\" (or --{key})")
                    raise ValueError(f"no setting {key!r}, it has: {', '.join(s.key for s in cls.SETTINGS) or 'none'}")
                s.parse(value)
            if p.link:
                if cls.LINK_DOMAIN is None:
                    raise ValueError("it can not be linked")
                dom, first = domains.setdefault(p.link, (cls.LINK_DOMAIN, where))
                if dom != cls.LINK_DOMAIN:
                    raise ValueError(f"can not share link {p.link!r} with {first}")
            if p.markers and not cls.MARKERS:
                raise ValueError("it does not carry markers")
            for m in p.markers:
                params = {k: v for k, v in m.items() if k != "kind"}
                if m["kind"] not in MARKER_KINDS:
                    raise ValueError(f"unknown marker kind {m['kind']!r}, choose from: "
                                     f"{', '.join(MARKER_KINDS.names())} ({EXT_HINT})")
                kind = MARKER_KINDS.get(m["kind"])
                for key, value in params.items():
                    s = by_key(kind.PARAMS, key)
                    if s is None:
                        raise ValueError(f"marker {m['kind']} has no setting {key!r}")
                    s.parse(value)
        except ValueError as e:
            raise ValueError(f"{where}: {e}") from None
