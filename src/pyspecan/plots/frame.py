"""Frames: what a plot hands to a view

A plot is pure compute, it turns samples into a `Frame`. A frame says what to
draw (traces, images, axis ranges) and nothing about how, so the same frame can
be drawn by the browser, matplotlib, or a terminal.

Axis ranges left as None mean "autorange".
"""
import base64
from dataclasses import dataclass, field

import numpy as np

# colors, as hex strings
YELLOW = "#e6d84a"
RED = "#d9534f"
BLUE = "#5b9bd5"
GREEN = "#5cb85c"

# drawing features a view has to support to show a plot
LINE = "line"
SCATTER = "scatter"
IMAGE = "image"
THREE_D = "3d"

@dataclass
class Trace:
    """A line or scatter. With `x` None, point i is at xmin + i * (xmax - xmin) / len(y) (one point per
    bin, at the bin's frequency), or at i on an axis without an x range"""
    y: np.ndarray
    x: np.ndarray | None = None
    z: np.ndarray | None = None  # only for 3d axes
    color: str = YELLOW
    kind: str = LINE             # LINE or SCATTER
    name: str = ""               # stable id, lets a view update an artist instead of recreating it
    alpha: float = 1.0
    width: float = 1.5

@dataclass
class Marker:
    """A labeled mark in data coordinates. kind "point": a triangle at (x, y) with the label, "vline": a vertical
    line at x, "hline": a horizontal line at y (a level: trigger, threshold).

    `edit` is the setting dragging it changes: x for points and vlines, y for hlines. It belongs to marker
    `owner`, or to the plot itself when `owner` is "" (the scope's trigger level)"""
    x: float
    y: float = 0.0
    label: str = ""
    color: str = YELLOW
    kind: str = "point"          # "point" | "vline" | "hline"
    owner: str = ""              # id of the marker it belongs to, "" for the plot
    edit: str = ""               # the setting dragging it changes, "" when it can not be dragged

@dataclass
class Band:
    """A shaded x span (channel, adjacent channel, occupied bandwidth edges), or a box when it has a y span.
    ylo / yhi left None reach the edge of the axis; on an image axis without a y range they are ignored.
    On a 3d axis the box is drawn on the x / y floor"""
    lo: float
    hi: float
    color: str = BLUE
    alpha: float = 0.15
    label: str = ""
    owner: str = ""              # id of the marker it belongs to
    edit: tuple[str, str] | None = None # the (center, width) settings dragging its body / edges change, None when fixed
    ylo: float | None = None
    yhi: float | None = None

@dataclass
class TableRow:
    id: str                      # the marker this row belongs to, "" for a continuation row of the one above
    cells: list[str]

@dataclass
class Table:
    """The marker / measurement table, views show it only when it has rows"""
    columns: list[str]
    rows: list[TableRow] = field(default_factory=list)

@dataclass
class Image:
    """A heat map covering the axis' x/y range, row 0 is the top row

    scroll=False: `data` is the whole image (rows, cols).
    scroll=True:  `data` holds the newest rows (n, cols) ordered oldest first, they are
                  pushed onto the top of a history `rows` tall. Use `Scroller` to keep the history.
    """
    data: np.ndarray
    cmap: str = "magma"
    scroll: bool = False
    rows: int = 0
    clear: bool = False

@dataclass
class Surface:
    """A height field over a 3d axis' x / y range, drawn as a solid surface colored by height (a 3d surface
    spectrogram). data (rows, cols) uint8: 0 is zmin, 255 is zmax. Row 0 is at ymin, column 0 at xmin"""
    data: np.ndarray
    cmap: str = "magma"

@dataclass
class Axis:
    xmin: float | None = None
    xmax: float | None = None
    ymin: float | None = None
    ymax: float | None = None
    zmin: float | None = None
    zmax: float | None = None
    xfmt: str = "num"            # "freq" | "time" (seconds) | "num"
    yfmt: str = "num"            # "freq" | "num" | "log10" (y is log10 of the value, labeled like 1e-3)
    xlabel: str = ""
    ylabel: str = ""
    xlog: bool = False           # x on a log scale (offsets in a phase noise plot), its range must be positive
    square: bool = False
    projection: str = "2d"       # "2d" | "3d"
    aspect: tuple | None = None  # 3d box aspect
    offscale: str | None = None  # "above" | "below": the data is outside the y range
    traces: list[Trace] = field(default_factory=list)
    image: Image | None = None
    surface: Surface | None = None   # 3d axes only
    markers: list[Marker] = field(default_factory=list)
    bands: list[Band] = field(default_factory=list)

@dataclass
class Frame:
    axes: list[Axis]
    title: str = ""
    readout: list[tuple[str, str]] = field(default_factory=list) # (label, value) facts about the plot (RBW, averaging, stats)
    table: Table | None = None   # markers and measurements
    ptime: float = 0.0           # seconds spent computing, set by the controller

    def features(self) -> set[str]:
        """The drawing features this frame uses"""
        feats = set()
        for ax in self.axes:
            if ax.projection == "3d":
                feats.add(THREE_D)
            if ax.image is not None:
                feats.add(IMAGE)
            feats.update(t.kind for t in ax.traces)
        return feats

    def to_dict(self, digits=2) -> dict:
        """json-serializable form, for the web view"""
        return {"title": self.title, "ptime": self.ptime, "readout": [[str(k), str(v)] for k, v in self.readout],
                "table": None if self.table is None else {
                    "columns": list(self.table.columns), "rows": [{"id": r.id, "cells": [str(c) for c in r.cells]} for r in self.table.rows]},
                "axes": [_axis_dict(ax, digits) for ax in self.axes]}

def _list(arr, digits):
    return np.round(np.asarray(arr, dtype=np.float64), digits).tolist()

def _x_digits(ax: Axis, x, digits: int) -> int:
    """Decimals to keep of x values: relative to the axis span (seconds on a scope are tiny, Hz are large)"""
    span = (ax.xmax - ax.xmin) if ax.xmin is not None and ax.xmax is not None else float(np.ptp(x)) if len(x) else 0.0
    if not np.isfinite(span) or span <= 0:
        return digits + 2
    return max(0, digits + 2 - int(np.floor(np.log10(span))))

def _opt(v):
    return None if v is None else float(v)

def _axis_dict(ax: Axis, digits) -> dict:
    d = {k: getattr(ax, k) for k in (
        "xmin", "xmax", "ymin", "ymax", "zmin", "zmax", "xfmt", "yfmt", "xlabel", "ylabel", "xlog",
        "square", "projection", "aspect", "offscale")}
    d["traces"] = []
    for t in ax.traces:
        td = {"y": _list(t.y, digits), "color": t.color, "kind": t.kind, "alpha": t.alpha, "width": t.width}
        if t.x is not None:
            td["x"] = _list(t.x, _x_digits(ax, t.x, digits))
        if t.z is not None:
            td["z"] = _list(t.z, digits)
        d["traces"].append(td)
    d["markers"] = [{"x": float(m.x), "y": float(m.y), "label": m.label, "color": m.color, "kind": m.kind, "owner": m.owner, "edit": m.edit} for m in ax.markers]
    d["bands"] = [{"lo": float(b.lo), "hi": float(b.hi), "ylo": _opt(b.ylo), "yhi": _opt(b.yhi), "color": b.color, "alpha": b.alpha,
                   "label": b.label, "owner": b.owner, "edit": list(b.edit) if b.edit else None} for b in ax.bands]
    if ax.surface is not None:
        data = np.ascontiguousarray(ax.surface.data, dtype=np.uint8)
        d["surface"] = {"data": base64.b64encode(data.tobytes()).decode(), "rows": data.shape[0], "cols": data.shape[1],
                        "cmap": ax.surface.cmap}
    if ax.image is not None:
        im = ax.image
        data = np.ascontiguousarray(im.data, dtype=np.uint8)
        d["image"] = {
            "data": base64.b64encode(data.tobytes()).decode(), "rows_in": data.shape[0], "cols": data.shape[1],
            "cmap": im.cmap, "scroll": im.scroll, "rows": im.rows, "clear": im.clear,
        }
    return d

def time_unit(span: float) -> tuple[float, str]:
    """(scale, name) of the unit that shows times up to `span` seconds, for xfmt "time" """
    for scale, name in ((1.0, "s"), (1e-3, "ms"), (1e-6, "µs")):
        if span >= scale:
            return scale, name
    return 1e-9, "ns"

def fmt_time(v: float, span: float | None = None) -> str:
    """Seconds as text, in the unit of `span` (default: of v itself)"""
    scale, name = time_unit(abs(v) if span is None else abs(span))
    return f"{v/scale:.4g} {name}"

class Scroller:
    """Keeps the history of a scrolling Image for views that draw whole images"""
    def __init__(self):
        self.buf: np.ndarray | None = None

    def apply(self, im: Image) -> np.ndarray:
        """Push the image's new rows, returns the (rows, cols) history, newest on top"""
        data = np.asarray(im.data, dtype=np.uint8)
        n, w = data.shape
        if not im.scroll:
            self.buf = data
            return data
        if im.clear or self.buf is None or self.buf.shape != (im.rows, w):
            self.buf = np.zeros((im.rows, w), dtype=np.uint8)
        if n >= im.rows:
            self.buf[:] = data[-im.rows:][::-1]
        elif n:
            self.buf[n:] = self.buf[:-n].copy()
            self.buf[:n] = data[::-1]
        return self.buf
