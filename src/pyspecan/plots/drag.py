"""Drawing, moving and resizing markers with a mouse, independent of the view

The python side of what the web view does in app.js (hitTest, dragged, commitDrag), for views drawn in
python (tk). A view maps between data x and its own pixels, these functions do the rest:

- `hit_test` finds the marker or band edge under the pointer
- `Drag.to` follows the pointer
- `preview` draws the dragged axis before the plot hears about it
- `commit` turns a finished drag into the marker add / set to send
"""
from dataclasses import dataclass, replace
from typing import Callable

from .frame import GREEN, Axis, Band

TOOLS = ("channel", "acpr", "obw", "point", "off") # what dragging over empty space draws, a click draws a point
EDGE_PX = 6     # how near (pixels) a band edge or marker has to be to grab it
MIN_DRAG_PX = 6 # a drag narrower than this draws nothing
MARK_PX = 12    # how near (pixels, vertically) a point marker's triangle has to be

@dataclass
class Drag:
    """A press on an axis: grabbing a marker ("marker"), a band edge ("left" / "right") or body ("move"),
    or drawing a new marker ("new")"""
    i: int                       # axis index
    mode: str
    lo: float
    hi: float
    owner: str = ""
    edit: str | tuple[str, str] | None = None
    start: float = 0.0           # data x where it started
    lo0: float = 0.0
    hi0: float = 0.0
    moved: bool = False
    committed: bool = False      # sent, kept on screen until the plot's answer arrives

    def __post_init__(self):
        self.lo0, self.hi0 = self.lo, self.hi

    def to(self, x: float, px_moved: float):
        """Follow the pointer to data x, `px_moved`: how far in pixels it is from the start"""
        if self.mode == "left":
            self.lo = min(x, self.hi)
        elif self.mode == "right":
            self.hi = max(x, self.lo)
        elif self.mode == "move":
            dx = x - self.start
            self.lo, self.hi = self.lo0 + dx, self.hi0 + dx
        elif self.mode == "marker":
            self.lo = self.hi = x
        else: # new: lo is where it started
            self.hi = x
        self.moved = self.moved or abs(px_moved) > 2

    @property
    def span(self) -> tuple[float, float]:
        return min(self.lo, self.hi), max(self.lo, self.hi)

def hit_test(axis: Axis, i: int, to_px: Callable[[float], float], px: float,
             py: float | None = None, to_py: Callable[[float], float] | None = None) -> Drag | None:
    """The draggable marker or band under the pointer at pixel (px, py) of axis `i`, None for empty space.
    Point markers come first (they sit on top of bands); on an axis with levels (`to_py` given) the pointer
    has to be near the triangle too. Then band edges (the nearer one), then band bodies, the last drawn first"""
    image = axis.image is not None or to_py is None or py is None
    for m in axis.markers:
        if not m.edit or abs(to_px(m.x) - px) > EDGE_PX:
            continue
        if m.kind == "vline" or image or abs(to_py(m.y) - py) <= MARK_PX: # type: ignore[misc]
            return Drag(i, "marker", m.x, m.x, m.owner, m.edit)
    bands = [b for b in axis.bands if b.edit][::-1]
    for b in bands:
        a, z = to_px(b.lo), to_px(b.hi)
        near_a, near_z = abs(a - px) <= EDGE_PX, abs(z - px) <= EDGE_PX
        if near_a and (not near_z or abs(a - px) <= abs(z - px)):
            return Drag(i, "left", b.lo, b.hi, b.owner, b.edit)
        if near_z:
            return Drag(i, "right", b.lo, b.hi, b.owner, b.edit)
    for b in bands:
        if to_px(b.lo) < px < to_px(b.hi):
            return Drag(i, "move", b.lo, b.hi, b.owner, b.edit)
    return None

def preview(axis: Axis, drag: Drag | None, i: int) -> Axis:
    """`axis` (axis `i`) with what is being dragged where the pointer is. The axis given is not changed"""
    if drag is None or drag.i != i:
        return axis
    lo, hi = drag.span
    if drag.mode == "new":
        return replace(axis, bands=[*axis.bands, Band(lo, hi, GREEN, 0.15, "", edit=("freq", "bw"))])
    if drag.mode == "marker":
        return replace(axis, markers=[replace(m, x=drag.lo) if m.owner == drag.owner and m.edit else m for m in axis.markers])
    return replace(axis, bands=[replace(b, lo=lo, hi=hi) if b.owner == drag.owner and b.edit and b.edit[1] == drag.edit[1] else b # type: ignore[index]
                                for b in axis.bands])

def settled(axis: Axis, drag: Drag) -> bool:
    """Does `axis` (a frame drawn after the drag was sent) show the dropped geometry, so the preview can go.
    Markers snap to bins, so near is enough: within half a percent of the axis"""
    if drag.mode == "new":
        return True
    tol = abs((axis.xmax or 0.0) - (axis.xmin or 0.0)) * 0.005 or 1.0
    if drag.mode == "marker":
        return any(m.owner == drag.owner and m.edit and abs(m.x - drag.lo) <= tol for m in axis.markers)
    lo, hi = drag.span
    return any(b.owner == drag.owner and b.edit and abs(b.lo - lo) <= tol and abs(b.hi - hi) <= tol for b in axis.bands)

def hz(v: float) -> str:
    """A plain number of Hz, marker settings parse it like "1.2M" """
    return f"{v:.1f}"

def commit(tool: str, drag: Drag, wide: bool) -> tuple[str, str, dict] | None:
    """What a finished drag means: ("add", kind, params), ("set", marker id, params), or None for nothing.
    `wide`: the drag covered at least MIN_DRAG_PX pixels. A plain click on an existing marker does nothing"""
    lo, hi = drag.span
    if drag.mode == "new":
        if tool == "point" and not wide:
            return "add", "point", {"freq": hz(drag.hi)}
        if tool in ("channel", "acpr", "obw") and wide:
            key = "span" if tool == "obw" else "bw"
            return "add", tool, {"freq": hz((lo + hi) / 2), key: hz(hi - lo)}
        return None
    if not drag.moved:
        return None
    if drag.mode == "marker":
        return "set", drag.owner, {drag.edit: hz(drag.lo)} # type: ignore[dict-item]
    center, width = drag.edit # type: ignore[misc]
    return "set", drag.owner, {center: hz((lo + hi) / 2), width: hz(max(hi - lo, 1.0))}
