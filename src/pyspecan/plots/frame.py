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
    y: np.ndarray
    x: np.ndarray | None = None  # None -> evenly spaced across the x range
    z: np.ndarray | None = None  # only for 3d axes
    color: str = YELLOW
    kind: str = LINE             # LINE or SCATTER
    name: str = ""               # stable id, lets a view update an artist instead of recreating it
    alpha: float = 1.0
    width: float = 1.5

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
class Axis:
    xmin: float | None = None
    xmax: float | None = None
    ymin: float | None = None
    ymax: float | None = None
    zmin: float | None = None
    zmax: float | None = None
    xfmt: str = "num"            # "freq" | "num"
    yfmt: str = "num"
    xlabel: str = ""
    ylabel: str = ""
    square: bool = False
    projection: str = "2d"       # "2d" | "3d"
    aspect: tuple | None = None  # 3d box aspect
    offscale: str | None = None  # "above" | "below": the data is outside the y range
    traces: list[Trace] = field(default_factory=list)
    image: Image | None = None

@dataclass
class Frame:
    axes: list[Axis]
    title: str = ""
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
        return {"title": self.title, "ptime": self.ptime, "axes": [_axis_dict(ax, digits) for ax in self.axes]}

def _list(arr, digits):
    return np.round(np.asarray(arr, dtype=np.float64), digits).tolist()

def _axis_dict(ax: Axis, digits) -> dict:
    d = {k: getattr(ax, k) for k in (
        "xmin", "xmax", "ymin", "ymax", "zmin", "zmax", "xfmt", "yfmt", "xlabel", "ylabel",
        "square", "projection", "aspect", "offscale")}
    d["traces"] = []
    for t in ax.traces:
        td = {"y": _list(t.y, digits), "color": t.color, "kind": t.kind, "alpha": t.alpha, "width": t.width}
        if t.x is not None:
            td["x"] = _list(t.x, digits + 2)
        if t.z is not None:
            td["z"] = _list(t.z, digits)
        d["traces"].append(td)
    if ax.image is not None:
        im = ax.image
        data = np.ascontiguousarray(im.data, dtype=np.uint8)
        d["image"] = {
            "data": base64.b64encode(data.tobytes()).decode(), "rows_in": data.shape[0], "cols": data.shape[1],
            "cmap": im.cmap, "scroll": im.scroll, "rows": im.rows, "clear": im.clear,
        }
    return d

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
