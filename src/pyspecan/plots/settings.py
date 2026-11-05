"""Declarative plot settings

A plot declares what the user can change once, as `Setting`s. Defaults,
parsing and validation live here, and every view builds its widgets from the
same descriptors (html inputs, tk widgets, console commands).
"""
from dataclasses import dataclass, replace
from typing import Any, Callable

KINDS = ("number", "int", "text", "select", "check")

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

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"unknown setting kind {self.kind!r}")

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
        d = {"key": self.key, "label": self.label, "kind": "number" if self.kind == "int" else self.kind}
        if self.kind == "int":
            d["step"] = 1
        for k in ("min", "max", "step", "hint"):
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
