"""Draw frames as text, no plotting libraries

Traces are drawn with braille characters (2x4 dots per cell), images with half
blocks (two pixels per cell) in 24-bit color, or a character ramp without color.
`draw_frame` returns lines of text, the caller decides where they go.
"""
import numpy as np

from ...plots import colormap
from ...plots.frame import Axis, Frame, Trace

RESET = "\x1b[0m"
DIM = "\x1b[2m"
RAMP = " .:-=+*#%@"

# braille dot bits, [dot column][dot row]
_BITS = ((0x01, 0x02, 0x04, 0x40), (0x08, 0x10, 0x20, 0x80))

def _rgb(hexcolor: str) -> tuple[int, int, int]:
    h = hexcolor.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

def _fg(rgb) -> str:
    return "\x1b[38;2;%d;%d;%dm" % rgb

def _bg(rgb) -> str:
    return "\x1b[48;2;%d;%d;%dm" % rgb

# --- number formatting --- #
def fmt_hz(v: float) -> str:
    for scale, suffix in ((1e9, "G"), (1e6, "M"), (1e3, "k")):
        if abs(v) >= scale:
            return f"{v/scale:.3f}".rstrip("0").rstrip(".") + suffix
    return f"{v:.0f}"

def fmt_num(v: float) -> str:
    if v != 0 and (abs(v) >= 10000 or abs(v) < 0.01):
        return f"{v:.1e}"
    return f"{v:.2f}".rstrip("0").rstrip(".") if abs(v) < 100 else f"{v:.0f}"

# --- braille canvas --- #
class Canvas:
    """cols x rows characters, each a 2x4 dot grid"""
    def __init__(self, cols: int, rows: int):
        self.cols, self.rows = cols, rows
        self.w, self.h = cols * 2, rows * 4
        self.bits = np.zeros((rows, cols), dtype=np.uint16)
        self.color: list[list] = [[None] * cols for _ in range(rows)]

    def dot(self, x: int, y: int, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            r, c = y >> 2, x >> 1
            self.bits[r, c] |= _BITS[x & 1][y & 3]
            self.color[r][c] = color

    def line(self, x0: int, y0: int, x1: int, y1: int, color):
        """Bresenham"""
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        for _ in range(dx - dy + 2): # bounded, never loops forever on bad input
            self.dot(x0, y0, color)
            if x0 == x1 and y0 == y1:
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def lines(self, use_color: bool) -> list[str]:
        out = []
        for r in range(self.rows):
            parts, prev = [], None
            for c in range(self.cols):
                bits = int(self.bits[r, c])
                col = self.color[r][c] if use_color and bits else None
                if col != prev:
                    parts.append(RESET if col is None else _fg(_rgb(col)))
                    prev = col
                parts.append(chr(0x2800 + bits))
            if prev is not None:
                parts.append(RESET)
            out.append("".join(parts))
        return out

# --- axes --- #
def _extent(lo, hi, arrays, pad=0.05):
    if lo is not None and hi is not None:
        return float(lo), float(hi)
    vals = [a[np.isfinite(a)] for a in arrays if len(a)]
    vals = [v for v in vals if len(v)]
    if not vals:
        return (0.0, 1.0) if lo is None or hi is None else (lo, hi)
    mn, mx = min(v.min() for v in vals), max(v.max() for v in vals)
    if mn == mx:
        mn, mx = mn - 0.5, mx + 0.5
    p = (mx - mn) * pad
    return (float(mn - p) if lo is None else lo), (float(mx + p) if hi is None else hi)

def _scale(v, lo, hi, n):
    """data -> dot coordinate in 0..n-1"""
    return np.clip(np.round((np.asarray(v, dtype=np.float64) - lo) / ((hi - lo) or 1.0) * (n - 1)), 0, n - 1).astype(int)

def _draw_trace(cv: Canvas, t: Trace, xr, yr, use_color):
    y = np.asarray(t.y, dtype=np.float64)
    ok = np.isfinite(y)
    if not ok.any():
        return
    py = (cv.h - 1) - _scale(np.where(ok, y, yr[0]), yr[0], yr[1], cv.h)
    n = len(y)
    if t.x is None:
        px = _scale(np.arange(n), 0, max(n - 1, 1), cv.w)
    else:
        px = _scale(t.x, xr[0], xr[1], cv.w)
    if t.kind == "scatter":
        for a, b, k in zip(px, py, ok):
            if k:
                cv.dot(int(a), int(b), t.color)
        return
    if t.x is None and n > cv.w: # more points than dot columns: draw each column's min..max
        edges = np.linspace(0, n, cv.w + 1).astype(int)
        prev = None
        for c in range(cv.w):
            seg = py[edges[c]:max(edges[c + 1], edges[c] + 1)]
            lo, hi = int(seg.min()), int(seg.max())
            if prev is not None: # reach back to the previous column so the line stays connected
                lo, hi = min(lo, prev), max(hi, prev)
            cv.line(c, lo, c, hi, t.color)
            prev = int(seg[-1])
        return
    for i in range(1, n):
        if ok[i] and ok[i - 1]:
            cv.line(int(px[i - 1]), int(py[i - 1]), int(px[i]), int(py[i]), t.color)

def _resample(data: np.ndarray, rows: int, cols: int) -> np.ndarray:
    """Shrink (or stretch) to rows x cols, keeping the peak of every bin"""
    out = data
    for axis, n in ((0, rows), (1, cols)):
        src = out.shape[axis]
        if n < src:
            edges = np.linspace(0, src, n + 1).astype(int)[:-1]
            out = np.maximum.reduceat(out, edges, axis=axis)
        elif n > src:
            idx = np.minimum((np.arange(n) * src // n), src - 1)
            out = np.take(out, idx, axis=axis)
    return out

def _draw_image(data: np.ndarray, cmap: str, cols: int, rows: int, use_color: bool) -> list[str]:
    img = _resample(np.asarray(data, dtype=np.uint8), rows * 2, cols)
    lut = colormap.lut(cmap)
    out = []
    for r in range(rows):
        top, bot = img[2 * r], img[2 * r + 1]
        if use_color:
            parts = [f"{_fg(tuple(lut[a]))}{_bg(tuple(lut[b]))}▀" for a, b in zip(top.tolist(), bot.tolist())]
            out.append("".join(parts) + RESET)
        else:
            avg = (top.astype(np.int32) + bot) // 2
            out.append("".join(RAMP[min(int(v) * len(RAMP) // 256, len(RAMP) - 1)] for v in avg))
    return out

def draw_axis(ax: Axis, image_data, width: int, height: int, use_color=True) -> list[str]:
    """One axis in a width x height box of text"""
    is_image = ax.image is not None
    show_y = not is_image or ax.ymin is not None
    arrays_y = [np.asarray(t.y, dtype=np.float64) for t in ax.traces]
    arrays_x = [np.asarray(t.x, dtype=np.float64) if t.x is not None else np.arange(len(t.y), dtype=np.float64) for t in ax.traces]
    xr = _extent(ax.xmin, ax.xmax, arrays_x)
    yr = _extent(ax.ymin, ax.ymax, arrays_y) if show_y else (0.0, 1.0)

    # y labels, evenly spaced rows
    plot_rows = max(height - 1, 1)
    ticks = max(2, min(8, plot_rows // 3 + 1)) if show_y else 0
    labels: dict[int, str] = {}
    for i in range(ticks):
        row = round(i * (plot_rows - 1) / (ticks - 1))
        labels[row] = fmt_num(yr[1] - i / (ticks - 1) * (yr[1] - yr[0]))
    lw = min(max((len(s) for s in labels.values()), default=0) + 1, 10)
    cols = max(width - lw - 1, 4)
    if ax.square: # a braille cell is 2 dots wide, 4 tall: twice the columns make a square
        cols = min(cols, plot_rows * 2)

    # plot area
    if is_image:
        body = _draw_image(image_data if image_data is not None else ax.image.data, ax.image.cmap, cols, plot_rows, use_color)
    else:
        cv = Canvas(cols, plot_rows)
        for t in ax.traces:
            _draw_trace(cv, t, xr, yr, use_color)
        body = cv.lines(use_color)
    if ax.offscale:
        marker = "^ above range" if ax.offscale == "above" else "v below range"
        row = 0 if ax.offscale == "above" else len(body) - 1
        body[row] = (DIM + marker + RESET if use_color else marker) + _skip_visible(body[row], len(marker))

    lines = []
    for r, row in enumerate(body):
        label = labels.get(r, "")[:lw - 1].rjust(lw - 1)
        lines.append(f"{label}│{row}")

    # x labels
    fmt = fmt_hz if ax.xfmt == "freq" else fmt_num
    n = 5 if cols >= 50 else 3
    axis_row = [" "] * (lw + cols)
    for i in range(n):
        text = fmt(xr[0] + i / (n - 1) * (xr[1] - xr[0]))
        start = lw + round(i / (n - 1) * (cols - 1)) - (0 if i == 0 else len(text) if i == n - 1 else len(text) // 2)
        start = max(0, min(start, len(axis_row) - len(text)))
        axis_row[start:start + len(text)] = text
    lines.append("".join(axis_row))
    return lines

def _skip_visible(line: str, n: int) -> str:
    """`line` without its first n visible characters (escape sequences are kept)"""
    out, seen, i = [], 0, 0
    while i < len(line):
        if line[i] == "\x1b":
            j = line.index("m", i) + 1
            out.append(line[i:j])
            i = j
        else:
            if seen >= n:
                out.append(line[i])
            seen += 1
            i += 1
    return "".join(out)

def draw_frame(frame: Frame, images: list, width: int, height: int, use_color=True) -> list[str]:
    """A frame as text lines in a width x height box. `images[i]` is axis i's full image data (see Scroller)"""
    title = frame.title[:width]
    lines = [DIM + title + RESET if use_color else title] if title else []
    avail = height - len(lines)
    n = max(len(frame.axes), 1)
    each = max(avail // n, 3)
    for i, ax in enumerate(frame.axes):
        lines += draw_axis(ax, images[i] if i < len(images) else None, width, each, use_color)
    return lines
