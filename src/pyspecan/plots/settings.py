"""Declarative plot settings

A plot declares what the user can change once, as `Setting`s. Defaults,
parsing and validation live here, and every view builds its widgets from the
same descriptors (html inputs, tk widgets, console commands).
"""
import importlib.util
import os
from dataclasses import dataclass, replace
from typing import Any, Callable

KINDS = ("number", "int", "text", "select", "check")
SCOPES = ("plot", "link", "global") # where a value lives: in the plot, shared by its link group, shared by every plot

@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    kind: str = "number"
    default: Any = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: tuple = ()
    hint: str = ""
    reset: bool = False            # changing it clears the plot's accumulated state
    coerce: Callable | None = None # custom parser for kind "text"
    flags: tuple = ()              # command line flags, exposes the setting as an argument
    help: str = ""
    group: str = "General"         # section views show it in
    scope: str = "plot"            # see SCOPES
    advanced: bool = False         # folded away under the section's "Advanced"

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"unknown setting kind {self.kind!r}")
        if self.scope not in SCOPES:
            raise ValueError(f"unknown setting scope {self.scope!r}")

    def with_(self, **changes) -> "Setting":
        return replace(self, **changes)

    def parse(self, value):
        """Validate `value` and return it as the setting's python type, raises ValueError"""
        if self.kind == "check":
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return bool(value)
        if self.kind == "select":
            if value not in self.options:
                raise ValueError(f"{self.label}: {value!r} is not one of {', '.join(map(str, self.options))}")
            return value
        if self.kind == "text":
            return self.coerce(value) if self.coerce else str(value)
        try:
            value = int(float(value)) if self.kind == "int" else float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{self.label}: {value!r} is not a number") from None
        if self.min is not None and value < self.min:
            raise ValueError(f"{self.label} must be at least {self.min:g}")
        if self.max is not None and value > self.max:
            raise ValueError(f"{self.label} must be at most {self.max:g}")
        return value

    def to_dict(self) -> dict:
        """json-serializable description for views"""
        d = {"key": self.key, "label": self.label, "kind": "number" if self.kind == "int" else self.kind,
             "group": self.group, "scope": self.scope, "advanced": self.advanced}
        if self.kind == "int":
            d["step"] = 1
        for k in ("min", "max", "step", "hint", "help"):
            v = getattr(self, k)
            if v not in (None, ""):
                d[k] = v
        if self.kind == "select":
            d["options"] = list(self.options)
        return d

def override(settings: tuple, **changes) -> tuple:
    """Copy of `settings` with per-key changes: override(S, vbw={"default": 0.0})"""
    out = []
    for s in settings:
        out.append(s.with_(**changes[s.key]) if s.key in changes else s)
    return tuple(out)

def without(settings: tuple, *keys) -> tuple:
    return tuple(s for s in settings if s.key not in keys)

def grouped(settings: tuple, **changes) -> tuple:
    """Copy of `settings` with the same changes for every one: grouped(S, group="Trace")"""
    return tuple(s.with_(**changes) for s in settings)

def by_key(settings, key: str) -> Setting | None:
    return next((s for s in settings if s.key == key), None)

def _have_rpps() -> bool:
    """Is the optional DSP library (rpps) installed. Found without importing it, the plots that use it import it
    when they first run. PYSPECAN_NO_RPPS=1 hides it"""
    if os.environ.get("PYSPECAN_NO_RPPS"):
        return False
    try:
        return importlib.util.find_spec("rpps") is not None
    except (ImportError, ValueError):
        return False

HAVE_RPPS = _have_rpps()

_TIME_PREFIX = {"n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3}

def parse_time(value) -> float:
    """'10u', '2.5ms', '1e-3', '' -> seconds, 0 for blank or 'auto'"""
    s = str(value).strip().lower().removesuffix("s").strip()
    if s in ("", "auto", "0"):
        return 0.0
    mul = 1.0
    if s[-1] in _TIME_PREFIX:
        s, mul = s[:-1], _TIME_PREFIX[s[-1]]
    try:
        v = float(s) * mul
    except ValueError:
        raise ValueError(f"{value!r} is not a time, use e.g. 10u, 2m, 0.5") from None
    if v < 0:
        raise ValueError("time must not be negative")
    return v

def time_text(value) -> str:
    """coerce for text settings holding a time, blank and 'auto' stay as given"""
    parse_time(value)
    return str(value).strip()

def _freq_text(value) -> str:
    """coerce for a frequency like '1.2M', blank stays blank"""
    from ..obj import Frequency
    s = str(value).strip()
    if s:
        Frequency.get(s)
    return s

# the signal the DSP plots analyse (pyspecan.plots.dsp), shared by every plot: picking a signal's box on any
# spectrum selects it for all of them
ANALYSIS_SETTINGS = (
    Setting("dsp_freq", "Signal freq", "text", default="", coerce=_freq_text, hint="strongest", flags=("--dsp_freq",),
            scope="global", group="Analysis", help="center of the signal the DSP plots analyse, blank for the strongest found"),
    Setting("dsp_bw", "Signal BW", "text", default="", coerce=_freq_text, hint="as found", flags=("--dsp_bw",),
            scope="global", group="Analysis", help="its bandwidth, blank for the width the signal search found"),
    Setting("dsp_mod", "Modulation", "select", default="auto", options=("auto", "bpsk", "qpsk", "8psk", "16QAM", "64QAM"),
            flags=("--dsp_mod",), scope="global", group="Analysis", help="the constellation to lock to, 'auto' finds it"),
    Setting("dsp_baud", "Symbol rate", "text", default="", coerce=_freq_text, hint="auto", flags=("--dsp_baud",),
            scope="global", group="Analysis", help="symbol rate when known, like 50k, blank to find it"),
)

# instrument wide, every plot reads the same values
GLOBAL_SETTINGS = (
    Setting("cal_db", "Cal (dBm @ 0 dBFS)", "number", default=0.0, step=1, reset=True, flags=("--cal_db",), scope="global", group="Calibration",
            help="dBm reading of a full scale tone, for the dBm units"),
    Setting("ext_gain", "Ext gain (dB)", "number", default=0.0, step=1, reset=True, flags=("--ext_gain",), scope="global", group="Calibration",
            help="gain ahead of the receiver, removed from dBm readings"),
) + (ANALYSIS_SETTINGS if HAVE_RPPS else ())
