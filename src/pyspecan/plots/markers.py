"""Markers and measurements on a frequency plot

A plot owns a `MarkerSet`: the markers the user added, each of a registered kind (point, peak,
delta, channel, acpr, obw) with its own parameters. Every render the plot hands the set its latest
unsmoothed trace and gets back what to draw (markers, shaded bands) and the table rows. Because
a marker only needs a trace, any frequency plot can carry them: the PSD, the spectrograms, ...

To add a kind, subclass `MarkerKind`, list its `PARAMS` (the same `Setting`s plots use, so views
build their editors from them) and register it with `@marker_kind("name")`.
"""
from dataclasses import dataclass, field

import numpy as np

from ..measure import channel, peaks, units
from ..utils.registry import Registry
from .frame import BLUE, GREEN, YELLOW, Band, Marker, Table, TableRow
from .freq import DENSITY_UNIT, POWER_UNIT, fmt_hz, freq_list_text, freq_text, hz, hz_list, optional_float
from .settings import Setting

MARKER_KINDS: Registry = Registry("marker kind")

def marker_kind(name: str):
    def deco(cls):
        cls.NAME = name
        return MARKER_KINDS.register(name)(cls)
    return deco

COLUMNS = ["", "Type", "Freq", "Result"]

@dataclass
class Context:
    """What a marker measures: the plot's latest full resolution trace (dB in the plot's unit)"""
    plot: object
    trace: np.ndarray
    freqs: np.ndarray
    found: dict = field(default_factory=dict) # id -> (freq, level) of the markers evaluated so far

    @property
    def n(self) -> int:
        return len(self.trace)

    @property
    def df(self) -> float:
        return self.plot.source.fs / self.n

    @property
    def unit(self) -> str:
        return self.plot.unit

    @property
    def cf(self) -> float:
        return self.plot.source.cf

    @property
    def edges(self) -> tuple[float, float]:
        return float(self.freqs[0] - self.df / 2), float(self.freqs[-1] + self.df / 2)

    def outside(self, lo: float, hi: float) -> bool:
        """The span [lo, hi] does not overlap the plot's frequency range at all (retuned away)"""
        e_lo, e_hi = self.edges
        return hi <= e_lo or lo >= e_hi

    def density(self) -> np.ndarray:
        return self.plot.density_lin(self.trace)

    def at(self, freq: float) -> tuple[float, float]:
        """(bin frequency, level) nearest `freq`"""
        i = int(np.clip(round((freq - self.freqs[0]) / self.df), 0, self.n - 1))
        return float(self.freqs[i]), float(self.trace[i])

    def level_text(self, level: float, noise: bool = False) -> str:
        """A level in the plot's unit, `noise` shows it per Hz (divided by the RBW)"""
        if noise and not units.is_density(self.unit):
            return f"{level - 10 * np.log10(self.plot.rbw(self.n)):.2f} {DENSITY_UNIT[self.unit]}"
        return f"{level:.2f} {self.unit}"

@dataclass
class Result:
    rows: list[list[str]]                 # [freq, result] cells, the first row carries the marker's id
    marks: list[Marker] = field(default_factory=list)
    bands: list[Band] = field(default_factory=list)
    at: tuple[float, float] | None = None # (freq, level), what a delta can refer to

class MarkerKind:
    NAME = ""
    PARAMS: tuple[Setting, ...] = ()
    COLOR = YELLOW

    def evaluate(self, ctx: Context, mid: str, p: dict) -> Result:
        raise NotImplementedError()

SETTING_NOISE = Setting("noise", "Per Hz", "check", default=False, help="show the level per Hz (divided by the RBW)")
SETTING_FREQ = Setting("freq", "Freq", "text", default="", coerce=freq_text, hint="center", help="frequency, like 1.2M")
SETTING_BW = Setting("bw", "Bandwidth", "text", default="", coerce=freq_text, hint="span / 10", help="bandwidth, like 200k")

@marker_kind("point")
class Point(MarkerKind):
    """A fixed frequency"""
    PARAMS = (SETTING_FREQ, SETTING_NOISE)

    def evaluate(self, ctx, mid, p):
        want = hz(p["freq"], ctx.cf)
        if ctx.outside(want, want):
            return Result([[fmt_hz(want), "outside span"]])
        f, lvl = ctx.at(want)
        return Result([[fmt_hz(f), ctx.level_text(lvl, p["noise"])]], [Marker(f, lvl, mid, self.COLOR, owner=mid, edit="freq")], at=(f, lvl))

@marker_kind("peak")
class Peak(MarkerKind):
    """Tracks the n-th highest peak"""
    COLOR = GREEN
    PARAMS = (
        Setting("rank", "Peak #", "int", default=1, min=1, max=64),
        Setting("threshold", "Threshold", "text", default="", coerce=optional_float, hint="off", help="minimum peak level"),
        Setting("excursion", "Excursion (dB)", "number", default=6.0, min=0, step=1, help="how far a peak must rise above its surroundings"),
        SETTING_NOISE,
    )

    def evaluate(self, ctx, mid, p):
        thr = float(p["threshold"]) if p["threshold"] else None
        found = peaks.find_peaks(ctx.trace, p["rank"], thr, p["excursion"])
        if len(found) < p["rank"]:
            return Result([["-", "no peak"]])
        pos, lvl = peaks.interp(ctx.trace, int(found[p["rank"] - 1]))
        f = float(ctx.freqs[0] + pos * ctx.df)
        return Result([[fmt_hz(f), ctx.level_text(lvl, p["noise"])]], [Marker(f, lvl, mid, self.COLOR)], at=(f, lvl))

@marker_kind("delta")
class Delta(MarkerKind):
    """A fixed frequency measured against another marker"""
    COLOR = BLUE
    PARAMS = (SETTING_FREQ, Setting("ref", "Reference", "text", default="M1", help="the marker to measure against, like M1"))

    def evaluate(self, ctx, mid, p):
        want = hz(p["freq"], ctx.cf)
        if ctx.outside(want, want):
            return Result([[fmt_hz(want), "outside span"]])
        f, lvl = ctx.at(want)
        mark = [Marker(f, lvl, mid, self.COLOR, owner=mid, edit="freq")]
        ref = ctx.found.get(str(p["ref"]).strip().upper())
        if ref is None:
            return Result([[fmt_hz(f), f"no marker {p['ref']}"]], mark, at=(f, lvl))
        return Result([[fmt_hz(f - ref[0]), f"{lvl - ref[1]:+.2f} dB"]], mark, at=(f, lvl))

class _Band(MarkerKind):
    """Measurements over a frequency span"""
    def span(self, ctx, p, key="bw") -> float:
        return hz(p[key], ctx.plot.source.fs / 10)

@marker_kind("channel")
class ChannelPower(_Band):
    """Power and mean density in a channel"""
    COLOR = GREEN
    PARAMS = (SETTING_FREQ, SETTING_BW)

    def evaluate(self, ctx, mid, p):
        c, bw = hz(p["freq"], ctx.cf), self.span(ctx, p)
        if ctx.outside(c - bw/2, c + bw/2):
            return Result([[f"{fmt_hz(c)} / {fmt_hz(bw)}", "outside span"]])
        power = channel.band_power(ctx.density(), ctx.freqs, c - bw/2, c + bw/2)
        u = ctx.unit
        return Result([
            [f"{fmt_hz(c)} / {fmt_hz(bw)}", f"{units.lin_to_db(power):.2f} {POWER_UNIT[u]}"],
            ["", f"{units.lin_to_db(power / bw):.2f} {DENSITY_UNIT[u]}"],
        ], [Marker(c, 0, mid, self.COLOR, kind="vline")], [Band(c - bw/2, c + bw/2, self.COLOR, label=mid, owner=mid, edit=("freq", "bw"))])

@marker_kind("acpr")
class ACPR(_Band):
    """Each adjacent channel against the main channel, in dBc"""
    COLOR = GREEN
    PARAMS = (
        SETTING_FREQ, SETTING_BW,
        Setting("adj_bw", "Adjacent BW", "text", default="", coerce=freq_text, hint="= bandwidth"),
        Setting("offsets", "Offsets", "text", default="", coerce=freq_list_text, hint="= bandwidth", help="adjacent channel center offsets, like '1M, 2M'"),
    )

    def evaluate(self, ctx, mid, p):
        c, bw = hz(p["freq"], ctx.cf), self.span(ctx, p)
        adj = hz(p["adj_bw"], bw)
        if ctx.outside(c - bw/2, c + bw/2):
            return Result([[f"{fmt_hz(c)} / {fmt_hz(bw)}", "outside span"]])
        offsets = [abs(o) for o in hz_list(p["offsets"])] or [bw]
        main, lower, upper = channel.acpr(ctx.density(), ctx.freqs, c, bw, offsets, adj)
        lo, hi = ctx.edges
        bands = [Band(c - bw/2, c + bw/2, self.COLOR, label=mid, owner=mid, edit=("freq", "bw"))]
        rows = [[f"{fmt_hz(c)} / {fmt_hz(bw)}", f"{units.lin_to_db(main):.2f} {POWER_UNIT[ctx.unit]}"]]
        for o, l, u in zip(offsets, lower, upper):
            for sign, dbc in ((-1, l), (1, u)):
                centre = c + sign * o
                inside = centre - adj/2 >= lo and centre + adj/2 <= hi # a channel cut by the span would read low
                label = ("-" if sign < 0 else "+") + fmt_hz(o)
                rows.append([label, f"{dbc:.2f} dBc" if inside else "outside span"])
                if lo <= centre <= hi:
                    bands.append(Band(centre - adj/2, centre + adj/2, BLUE, label=label))
        return Result(rows, [Marker(c, 0, mid, self.COLOR, kind="vline")], bands)

@marker_kind("obw")
class OBW(_Band):
    """Occupied bandwidth (the span holding pct % of the power) and the -x dB bandwidth"""
    COLOR = GREEN
    PARAMS = (
        SETTING_FREQ,
        Setting("span", "Span", "text", default="", coerce=freq_text, hint="whole band", help="range searched around the frequency"),
        Setting("pct", "Power %", "number", default=99.0, min=1, max=99.99, step=1),
        Setting("xdb", "x dB", "number", default=26.0, min=0.1, step=1),
    )

    def evaluate(self, ctx, mid, p):
        lo, hi = ctx.edges
        c = hz(p["freq"], ctx.cf)
        bands = []
        if p["span"] and ctx.outside(c - hz(p["span"], 0) / 2, c + hz(p["span"], 0) / 2):
            return Result([["span", "outside span"]])
        if p["span"]:
            half = hz(p["span"], 0) / 2
            bands.append(Band(c - half, c + half, YELLOW, alpha=0.04, owner=mid, edit=("freq", "span"))) # what the drag edits
            lo, hi = max(lo, c - half), min(hi, c + half)
        dens, freqs = ctx.density(), ctx.freqs
        f_lo, f_hi, total = channel.obw(dens, freqs, lo, hi, p["pct"])
        bands.append(Band(f_lo, f_hi, self.COLOR, label=mid))
        marks = [Marker(f_lo, kind="vline", color=self.COLOR), Marker(f_hi, kind="vline", color=self.COLOR)]
        rows = [[f"{p['pct']:g}%", fmt_hz(f_hi - f_lo)]]
        sel = np.flatnonzero((freqs >= lo) & (freqs <= hi))
        if len(sel) and total > 0:
            centroid = float(np.sum(freqs[sel] * dens[sel]) / np.sum(dens[sel]))
            peak = sel[int(np.argmax(ctx.trace[sel]))]
            x_lo, x_hi = channel.xdb_bw(ctx.trace, freqs, int(peak), p["xdb"])
            bands.append(Band(x_lo, x_hi, YELLOW, alpha=0.08))
            rows += [["centroid", f"{fmt_hz(centroid - c)} from center"], [f"-{p['xdb']:g} dB", fmt_hz(x_hi - x_lo)]]
        rows.append(["total", f"{units.lin_to_db(total):.2f} {POWER_UNIT[ctx.unit]}"])
        return Result(rows, marks, bands)

class MarkerSet:
    """The markers of one plot, or of every plot of a link, M1, M2, ... in the order they were added.
    A set holds no plot: each plot evaluates it against its own trace"""
    def __init__(self):
        self.items: dict[str, dict] = {} # id -> {"kind": name, "params": {...}}
        self._next = 1

    def __len__(self):
        return len(self.items)

    def copy(self) -> "MarkerSet":
        out = MarkerSet()
        out.items = {mid: {"kind": it["kind"], "params": dict(it["params"])} for mid, it in self.items.items()}
        out._next = self._next
        return out

    def merge(self, other: "MarkerSet"):
        """Take in the markers of `other` under new ids. Delta markers keep pointing at their renumbered reference"""
        renamed = {}
        for mid, it in other.items.items():
            renamed[mid] = f"M{self._next}"
            self._next += 1
        for mid, it in other.items.items():
            params = dict(it["params"])
            for k, v in params.items():
                if k == "ref" and isinstance(v, str) and v.strip().upper() in renamed:
                    params[k] = renamed[v.strip().upper()]
            self.items[renamed[mid]] = {"kind": it["kind"], "params": params}

    def _kind(self, name: str) -> MarkerKind:
        return MARKER_KINDS.get(name)()

    def add(self, kind: str, **params) -> str:
        cls = MARKER_KINDS.get(kind)
        values = {}
        for s in cls.PARAMS:
            values[s.key] = s.parse(params.pop(s.key, s.default))
        if params:
            raise ValueError(f"{kind} has no setting {', '.join(params)}")
        mid = f"M{self._next}"
        self._next += 1
        self.items[mid] = {"kind": kind, "params": values}
        return mid

    def _get(self, mid: str) -> dict:
        try:
            return self.items[str(mid).upper()]
        except KeyError:
            raise ValueError(f"unknown marker {mid!r}") from None

    def set_many(self, mid: str, values: dict):
        """Change several settings of a marker at once, all or none (a drag moves its center and width together)"""
        item = self._get(mid)
        params = {s.key: s for s in MARKER_KINDS.get(item["kind"]).PARAMS}
        parsed = {}
        for key, value in values.items():
            if key not in params:
                raise ValueError(f"{item['kind']} has no setting {key!r}")
            parsed[key] = params[key].parse(value)
        item["params"].update(parsed)

    def remove(self, mid: str):
        self._get(mid)
        del self.items[str(mid).upper()]

    def set(self, mid: str, key: str, value):
        item = self._get(mid)
        for s in MARKER_KINDS.get(item["kind"]).PARAMS:
            if s.key == key:
                item["params"][key] = s.parse(value)
                return
        raise ValueError(f"{item['kind']} has no setting {key!r}")

    def describe(self) -> list[dict]:
        """json-serializable markers with their editable settings, for views"""
        return [{"id": mid, "kind": it["kind"], "params": dict(it["params"]),
                 "fields": [s.to_dict() for s in MARKER_KINDS.get(it["kind"]).PARAMS]} for mid, it in self.items.items()]

    @staticmethod
    def kinds() -> dict[str, list[dict]]:
        return {name: [s.to_dict() for s in cls.PARAMS] for name, cls in MARKER_KINDS.items()}

    def evaluate(self, plot, trace: np.ndarray, freqs: np.ndarray) -> tuple[list[Marker], list[Band], Table | None]:
        """Markers and bands to draw and the table, for `plot`'s latest trace"""
        if not self.items:
            return [], [], None
        ctx = Context(plot, trace, freqs)
        marks, bands, rows = [], [], []
        for mid, it in self.items.items():
            kind = self._kind(it["kind"])
            res = kind.evaluate(ctx, mid, it["params"])
            if res.at is not None:
                ctx.found[mid] = res.at
            marks += res.marks
            bands += res.bands
            for k, cells in enumerate(res.rows):
                rows.append(TableRow(mid if k == 0 else "", [mid, it["kind"], *cells] if k == 0 else ["", "", *cells]))
        return marks, bands, Table(COLUMNS, rows)
