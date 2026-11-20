"""Draw frames as text, no plotting libraries

Traces are drawn with braille characters (2x4 dots per cell), images with half
blocks (two pixels per cell) in 24-bit color, or a character ramp without color.
`draw_frame` returns lines of text, the caller decides where they go.
"""
import numpy as np

from ...plots import colormap
from ...plots.frame import Axis, Band, Frame, Trace, fmt_time

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

def fmt_log10(v: float) -> str:
    """y values holding log10 of the quantity: -3 -> 1e-3"""
    m, e = f"{10.0 ** v:.0e}".split("e")
    return f"{m}e{int(e)}"

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
        self.over: dict[tuple[int, int], tuple[str, str | None]] = {} # (row, col) -> (char, color), drawn over the dots

    def dot(self, x: int, y: int, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            r, c = y >> 2, x >> 1
            self.bits[r, c] |= _BITS[x & 1][y & 3]
            self.color[r][c] = color

    def text(self, row: int, col: int, text: str, color):
        """Write characters over the cells, clipped to the canvas"""
        for k, ch in enumerate(text):
            if 0 <= row < self.rows and 0 <= col + k < self.cols:
                self.over[(row, col + k)] = (ch, color)

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
                ov = self.over.get((r, c))
                col = (ov[1] if ov else self.color[r][c] if bits else None) if use_color else None
                if col != prev:
                    parts.append(RESET if col is None else _fg(_rgb(col)))
                    prev = col
                parts.append(ov[0] if ov else chr(0x2800 + bits))
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

def _trace_x(t: Trace, ax: Axis) -> np.ndarray:
    """A trace's x values, see Trace: one point per bin across the x range, or the index"""
    if t.x is not None:
        return np.asarray(t.x, dtype=np.float64)
    n = len(t.y)
    if ax.xmin is None or ax.xmax is None:
        return np.arange(n, dtype=np.float64)
    return ax.xmin + np.arange(n) * ((ax.xmax - ax.xmin) / max(n, 1))

def _draw_trace(cv: Canvas, t: Trace, x, xr, yr, use_color):
    y = np.asarray(t.y, dtype=np.float64)
    ok = np.isfinite(y)
    if not ok.any():
        return
    py = (cv.h - 1) - _scale(np.where(ok, y, yr[0]), yr[0], yr[1], cv.h)
    n = len(y)
    px = _scale(x, xr[0], xr[1], cv.w)
    if t.kind == "scatter":
        for a, b, k in zip(px, py, ok, strict=True):
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

EDGE = "#6b6b6b"

def _band_rows(b: Band, yr, n: int) -> tuple[int, int]:
    """The (top, bottom) dot / pixel rows of a band's y span out of n, the whole height without one"""
    top = 0 if b.yhi is None else (n - 1) - int(_scale(b.yhi, yr[0], yr[1], n))
    btm = n - 1 if b.ylo is None else (n - 1) - int(_scale(b.ylo, yr[0], yr[1], n))
    return min(top, btm), max(top, btm)

def _draw_marks(cv: Canvas, ax: Axis, xr, yr):
    """Band edges and vline markers as dim vertical lines (a band with a y span as a box), hline markers
    as a dashed horizontal line, point markers as a triangle and label"""
    def col(v):
        return int(_scale(v, xr[0], xr[1], cv.w))
    for b in ax.bands:
        top, btm = _band_rows(b, yr, cv.h)
        for v in (b.lo, b.hi):
            if xr[0] <= v <= xr[1]:
                cv.line(col(v), top, col(v), btm, EDGE)
        if b.ylo is not None or b.yhi is not None:
            a, z = col(max(b.lo, xr[0])), col(min(b.hi, xr[1]))
            for r in (top, btm):
                cv.line(a, r, z, r, EDGE)
        if b.label and xr[0] <= b.lo <= xr[1]:
            cv.text(btm // 4, col(b.lo) // 2 + 1, b.label, b.color)
    for m in ax.markers:
        if m.kind == "hline":
            if yr[0] <= m.y <= yr[1]:
                r = (cv.h - 1) - int(_scale(m.y, yr[0], yr[1], cv.h))
                for c in range(0, cv.w, 3): # dashed
                    cv.dot(c, r, m.color)
                if m.label:
                    cv.text(r // 4, cv.cols - len(m.label), m.label, m.color)
            continue
        if not xr[0] <= m.x <= xr[1]:
            continue
        c = col(m.x) // 2
        if m.kind == "vline":
            cv.line(col(m.x), 0, col(m.x), cv.h - 1, m.color)
            continue
        row = (cv.h - 1 - int(_scale(m.y, yr[0], yr[1], cv.h))) // 4
        above = row > 0
        cv.text(row - 1 if above else row + 1, c, "▼" if above else "▲", m.color)
        cv.text(row - 1 if above else row + 1, c + 1, m.label, m.color)

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

def _draw_image(data: np.ndarray, cmap: str, cols: int, rows: int, use_color: bool) -> list[list[str]]:
    """rows x cols cells, each a half block (or a ramp character) with its own color codes"""
    img = _resample(np.asarray(data, dtype=np.uint8), rows * 2, cols)
    lut = colormap.lut(cmap)
    out = []
    for r in range(rows):
        top, bot = img[2 * r], img[2 * r + 1]
        if use_color:
            out.append([f"{_fg(tuple(lut[a]))}{_bg(tuple(lut[b]))}▀" for a, b in zip(top.tolist(), bot.tolist(), strict=True)])
        else:
            avg = (top.astype(np.int32) + bot) // 2
            out.append([RAMP[min(int(v) * len(RAMP) // 256, len(RAMP) - 1)] for v in avg])
    return out

def _join(cells: list[list[str]], use_color: bool) -> list[str]:
    return ["".join(row) + (RESET if use_color else "") for row in cells]

def _draw_image_marks(cells: list[list[str]], ax: Axis, xr, yr, use_color: bool):
    """Band edges and vline markers as vertical lines over an image, point markers (on a level axis) as a
    triangle and label, written over the cells"""
    rows = len(cells)
    cols = len(cells[0]) if rows else 0
    if not cols:
        return
    def col(v):
        return int(_scale(v, xr[0], xr[1], cols))
    def put(r, c, text, color):
        for k, ch in enumerate(text):
            if 0 <= r < rows and 0 <= c + k < cols:
                cells[r][c + k] = f"{RESET}{_fg(_rgb(color))}{ch}{RESET}" if use_color else ch
    def vline(v, color, top=0, btm=rows - 1):
        for r in range(top, btm + 1):
            put(r, col(v), "│", color)
    level = ax.ymin is not None # an image without a y range ignores y spans
    for b in ax.bands:
        top, btm = _band_rows(b, yr, rows * 2) if level else (0, rows * 2 - 1)
        top, btm = top // 2, btm // 2
        for v in (b.lo, b.hi):
            if xr[0] <= v <= xr[1]:
                vline(v, EDGE, top, btm)
        if level and (b.ylo is not None or b.yhi is not None):
            for r in (top, btm):
                for c in range(col(max(b.lo, xr[0])), col(min(b.hi, xr[1])) + 1):
                    put(r, c, "─", EDGE)
    for b in ax.bands:
        if b.label and xr[0] <= b.lo <= xr[1]:
            put(rows - 1, col(b.lo) + 1, b.label, b.color)
    for m in ax.markers:
        if m.kind == "hline":
            if level and yr[0] <= m.y <= yr[1]:
                r = (rows * 2 - 1 - int(_scale(m.y, yr[0], yr[1], rows * 2))) // 2
                for c in range(0, cols, 2):
                    put(r, c, "╌", m.color)
                if m.label:
                    put(r, cols - len(m.label), m.label, m.color)
            continue
        if not xr[0] <= m.x <= xr[1]:
            continue
        if m.kind == "vline" or ax.ymin is None: # no level axis: a point is only a frequency
            vline(m.x, m.color)
            if m.label:
                put(0, col(m.x) + 1, m.label, m.color)
            continue
        row = (rows * 2 - 1 - int(_scale(m.y, yr[0], yr[1], rows * 2))) // 2
        above = row > 0
        put(row - 1 if above else row + 1, col(m.x), ("▼" if above else "▲") + m.label, m.color)

def draw_axis(ax: Axis, image_data, width: int, height: int, use_color=True) -> list[str]:
    """One axis in a width x height box of text"""
    is_image = ax.image is not None
    show_y = not is_image or ax.ymin is not None
    arrays_y = [np.asarray(t.y, dtype=np.float64) for t in ax.traces]
    arrays_x = [_trace_x(t, ax) for t in ax.traces]
    xr = _extent(ax.xmin, ax.xmax, arrays_x)
    yr = _extent(ax.ymin, ax.ymax, arrays_y) if show_y else (0.0, 1.0)

    # y labels, evenly spaced rows
    plot_rows = max(height - 1, 1)
    ticks = max(2, min(8, plot_rows // 3 + 1)) if show_y else 0
    labels: dict[int, str] = {}
    for i in range(ticks):
        row = round(i * (plot_rows - 1) / (ticks - 1))
        fy = fmt_log10 if ax.yfmt == "log10" else fmt_hz if ax.yfmt == "freq" else fmt_num
        labels[row] = fy(yr[1] - i / (ticks - 1) * (yr[1] - yr[0]))
    lw = min(max((len(s) for s in labels.values()), default=0) + 1, 10)
    cols = max(width - lw - 1, 4)
    if ax.square: # a braille cell is 2 dots wide, 4 tall: twice the columns make a square
        cols = min(cols, plot_rows * 2)

    # plot area
    if is_image:
        cells = _draw_image(image_data if image_data is not None else ax.image.data, ax.image.cmap, cols, plot_rows, use_color)
        _draw_image_marks(cells, ax, xr, yr, use_color)
        body = _join(cells, use_color)
    else:
        cv = Canvas(cols, plot_rows)
        for t, x in zip(ax.traces, arrays_x, strict=True):
            _draw_trace(cv, t, x, xr, yr, use_color)
        _draw_marks(cv, ax, xr, yr)
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
    if ax.xfmt == "freq":
        fmt = fmt_hz
    elif ax.xfmt == "time":
        def fmt(v):
            return fmt_time(v, xr[1] - xr[0])
    else:
        fmt = fmt_num
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

def readout_lines(readout, width: int, limit: int, use_color=True) -> list[str]:
    """`label: value` items packed into lines of at most `width` characters, at most `limit` lines"""
    lines, cur = [], ""
    for label, value in readout:
        item = f"{label}: {value}"[:width]
        if cur and len(cur) + 2 + len(item) > width:
            lines.append(cur)
            cur = ""
        cur = f"{cur}  {item}" if cur else item
    if cur:
        lines.append(cur)
    lines = lines[:max(limit, 0)]
    return [DIM + line + RESET if use_color else line for line in lines]

def table_lines(table, width: int, limit: int, use_color=True) -> list[str]:
    """The marker table as aligned text rows, at most `limit` lines (a header plus rows)"""
    if table is None or not table.rows or limit < 2:
        return []
    rows = [[str(c) for c in r.cells] for r in table.rows]
    w = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    w[-1] = max(w[-1], 0)
    lines = ["  ".join(c.ljust(w[i]) for i, c in enumerate(r))[:width].rstrip() for r in rows]
    lines = lines[:limit]
    return [DIM + line + RESET if use_color and k and not rows[k][0] else line for k, line in enumerate(lines)]

def draw_frame(frame: Frame, images: list, width: int, height: int, use_color=True) -> list[str]:
    """A frame as text lines in a width x height box. `images[i]` is axis i's full image data (see Scroller)"""
    title = frame.title[:width]
    lines = [DIM + title + RESET if use_color else title] if title else []
    n = max(len(frame.axes), 1)
    ro = readout_lines(frame.readout, width, min(4, (height - len(lines) - 3 * n) // 2), use_color)
    tb = table_lines(frame.table, width, min(8, (height - len(lines) - len(ro) - 3 * n) // 2), use_color)
    ro += tb
    avail = height - len(lines) - len(ro)
    each = max(avail // n, 3)
    for i, ax in enumerate(frame.axes):
        lines += draw_axis(ax, images[i] if i < len(images) else None, width, each, use_color)
    return lines + ro
