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
from .frame import BLUE, GREEN, RED, YELLOW, Band, Marker, Table, TableRow
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

    def level_value(self, level: float, noise: bool = False) -> tuple[str, float, str]:
        """("level", the level, its unit) as level_text shows it, for Result.values"""
        if noise and not units.is_density(self.unit):
            return ("level", float(level - 10 * np.log10(self.plot.rbw(self.n))), DENSITY_UNIT[self.unit])
        return ("level", float(level), self.unit)

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
    values: list[tuple[str, float, str]] = field(default_factory=list) # (name, number, unit): what a trend plots

class MarkerKind:
    NAME = ""
    PARAMS: tuple[Setting, ...] = ()
    COLOR = YELLOW
    ACTIONS: tuple[str, ...] = () # what `act` does, views offer them as buttons

    def evaluate(self, ctx: Context, mid: str, p: dict) -> Result:
        raise NotImplementedError()

    def act(self, ctx: Context, mid: str, p: dict, action: str):
        """Change the params `p` by an action (a peak marker's next peak) on the plot's latest trace"""
        raise ValueError(f"{self.NAME} has no action {action!r}")

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
        return Result([[fmt_hz(f), ctx.level_text(lvl, p["noise"])]], [Marker(f, lvl, mid, self.COLOR, owner=mid, edit="freq")], at=(f, lvl),
                      values=[ctx.level_value(lvl, p["noise"])])

@marker_kind("peak")
class Peak(MarkerKind):
    """Lands on the highest peak and stays at that frequency. next / prev step down / up the peaks by level, left /
    right to the nearest peak below / above in frequency (an analyzer's Next Peak keys); dragging it moves it too.
    `track` follows the peak every frame instead, `rank` picks which (1 the highest)"""
    COLOR = GREEN
    ACTIONS = ("prev", "next", "left", "right")
    PARAMS = (
        SETTING_FREQ.with_(hint="highest peak", help="where it sits, set by the peak search (or by hand, like 1.2M)"),
        Setting("track", "Track", "check", default=False, help="follow the peak every frame instead of staying put"),
        Setting("rank", "Peak #", "int", default=1, min=1, max=64, advanced=True,
                help="which peak by level it lands on (or tracks): 1 the highest"),
        Setting("threshold", "Threshold", "text", default="", coerce=optional_float, hint="off", help="minimum peak level"),
        Setting("excursion", "Excursion (dB)", "number", default=6.0, min=0, step=1, help="how far a peak must rise above its surroundings"),
        SETTING_NOISE,
    )

    @staticmethod
    def _peaks(ctx, p) -> list[tuple[float, float]]:
        """(freq, level) of every peak over the threshold, highest first"""
        thr = float(p["threshold"]) if p["threshold"] else None
        out = []
        for i in peaks.find_peaks(ctx.trace, ctx.n, thr, p["excursion"]):
            pos, lvl = peaks.interp(ctx.trace, int(i))
            out.append((float(ctx.freqs[0] + pos * ctx.df), float(lvl)))
        return out

    def evaluate(self, ctx, mid, p):
        thr = float(p["threshold"]) if p["threshold"] else None
        line = [] if thr is None else [Marker(0.0, thr, f"{mid} thr", self.COLOR, kind="hline", owner=mid, edit="threshold")]
        if p["track"] or not p["freq"]:
            found = self._peaks(ctx, p)
            if len(found) < p["rank"]:
                return Result([["-", "no peak"]], line)
            f, lvl = found[p["rank"] - 1]
            if not p["track"]:
                p["freq"] = f"{f:.1f}" # found once: it stays here
        else:
            f = hz(p["freq"], ctx.cf)
            if ctx.outside(f, f):
                return Result([[fmt_hz(f), "outside span"]], line)
            lvl = float(np.interp(f, ctx.freqs, ctx.trace)) # at its frequency, whatever the trace does around it
        mark = Marker(f, lvl, mid, self.COLOR, owner=mid, edit="" if p["track"] else "freq")
        return Result([[fmt_hz(f), ctx.level_text(lvl, p["noise"])]], [mark, *line], at=(f, lvl),
                      values=[ctx.level_value(lvl, p["noise"]), ("freq", f, "Hz")])

    def act(self, ctx, mid, p, action):
        found = self._peaks(ctx, p)
        if not found:
            raise ValueError(f"{mid}: no peaks")
        f = hz(p["freq"], ctx.cf) if p["freq"] else found[0][0]
        here = float(np.interp(f, ctx.freqs, ctx.trace))
        on = [k for k, (pf, _) in enumerate(found) if abs(pf - f) <= 2 * ctx.df] # the peak it sits on
        if action in ("next", "prev"):
            if on:
                k = on[0] + (1 if action == "next" else -1)
                pick = found[k] if 0 <= k < len(found) else None
            elif action == "next": # off a peak: the highest one below where it is
                pick = next((q for q in found if q[1] < here), None)
            else:
                pick = next((q for q in reversed(found) if q[1] > here), None)
        else:
            side = [q for q in found if (q[0] < f - ctx.df / 2 if action == "left" else q[0] > f + ctx.df / 2)]
            pick = min(side, key=lambda q: abs(q[0] - f)) if side else None
        if pick is None:
            raise ValueError(f"{mid}: no peak {'lower' if action == 'next' else 'higher' if action == 'prev' else 'to the ' + action}")
        p["freq"], p["track"] = f"{pick[0]:.1f}", False

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
        return Result([[fmt_hz(f - ref[0]), f"{lvl - ref[1]:+.2f} dB"]], mark, at=(f, lvl), values=[("delta", lvl - ref[1], "dB")])

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
        ], [Marker(c, 0, mid, self.COLOR, kind="vline")], [Band(c - bw/2, c + bw/2, self.COLOR, label=mid, owner=mid, edit=("freq", "bw"))],
            values=[("power", float(units.lin_to_db(power)), POWER_UNIT[u])])

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
        values = [("power", float(units.lin_to_db(main)), POWER_UNIT[ctx.unit])]
        for o, l, u in zip(offsets, lower, upper, strict=True):
            for sign, dbc in ((-1, l), (1, u)):
                centre = c + sign * o
                inside = centre - adj/2 >= lo and centre + adj/2 <= hi # a channel cut by the span would read low
                label = ("-" if sign < 0 else "+") + fmt_hz(o)
                rows.append([label, f"{dbc:.2f} dBc" if inside else "outside span"])
                if inside:
                    values.append((label, float(dbc), "dBc"))
                if lo <= centre <= hi:
                    bands.append(Band(centre - adj/2, centre + adj/2, BLUE, label=label))
        return Result(rows, [Marker(c, 0, mid, self.COLOR, kind="vline")], bands, values=values)

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
        values = [("obw", float(f_hi - f_lo), "Hz")]
        sel = np.flatnonzero((freqs >= lo) & (freqs <= hi))
        if len(sel) and total > 0:
            centroid = float(np.sum(freqs[sel] * dens[sel]) / np.sum(dens[sel]))
            peak = sel[int(np.argmax(ctx.trace[sel]))]
            x_lo, x_hi = channel.xdb_bw(ctx.trace, freqs, int(peak), p["xdb"])
            bands.append(Band(x_lo, x_hi, YELLOW, alpha=0.08))
            rows += [["centroid", f"{fmt_hz(centroid - c)} from center"], [f"-{p['xdb']:g} dB", fmt_hz(x_hi - x_lo)]]
        rows.append(["total", f"{units.lin_to_db(total):.2f} {POWER_UNIT[ctx.unit]}"])
        return Result(rows, marks, bands, values=values)

def _power(ctx, lvl: float) -> float:
    """A tone's level in the plot's power unit: a density unit reads a tone low by the RBW"""
    if units.is_density(ctx.unit):
        return lvl + 10 * np.log10(ctx.plot.rbw(ctx.n))
    return lvl

def _strongest(ctx, n: int, excursion: float = 6.0) -> list[tuple[float, float]]:
    """(freq, level) of the n strongest peaks, refined between bins, strongest first"""
    out = []
    for i in peaks.find_peaks(ctx.trace, n, None, excursion):
        pos, lvl = peaks.interp(ctx.trace, int(i))
        out.append((float(ctx.freqs[0] + pos * ctx.df), float(lvl)))
    return out

def _level_near(ctx, freq: float, bins: int = 3) -> tuple[float, float]:
    """(freq, level) of the highest point within `bins` of freq (a harmonic or product a little off its ideal place)"""
    i = int(np.clip(round((freq - ctx.freqs[0]) / ctx.df), 0, ctx.n - 1))
    lo, hi = max(0, i - bins), min(ctx.n, i + bins + 1)
    k = lo + int(np.argmax(ctx.trace[lo:hi]))
    pos, lvl = peaks.interp(ctx.trace, k)
    return float(ctx.freqs[0] + pos * ctx.df), float(lvl)

@marker_kind("peaks")
class PeakTable(MarkerKind):
    """Peak table: the strongest peaks, strongest first"""
    COLOR = GREEN
    PARAMS = (
        Setting("count", "Peaks", "int", default=5, min=1, max=50),
        Setting("threshold", "Threshold", "text", default="", coerce=optional_float, hint="off", help="minimum peak level"),
        Setting("excursion", "Excursion (dB)", "number", default=6.0, min=0, step=1, help="how far a peak must rise above its surroundings"),
    )

    def evaluate(self, ctx, mid, p):
        thr = float(p["threshold"]) if p["threshold"] else None
        found = peaks.find_peaks(ctx.trace, p["count"], thr, p["excursion"])
        if not len(found):
            return Result([["-", "no peaks"]])
        rows, marks, at = [], [], None
        for k, i in enumerate(found, 1):
            pos, lvl = peaks.interp(ctx.trace, int(i))
            f = float(ctx.freqs[0] + pos * ctx.df)
            at = at or (f, lvl)
            rows.append([f"P{k} {fmt_hz(f)}", ctx.level_text(lvl)])
            marks.append(Marker(f, lvl, f"{mid}.{k}", self.COLOR))
        return Result(rows, marks, at=at, values=[ctx.level_value(at[1]), ("freq", at[0], "Hz")])

@marker_kind("harmonics")
class Harmonics(MarkerKind):
    """Harmonic distortion: the fundamental and its harmonics in dBc, and the total (THD)"""
    COLOR = YELLOW
    PARAMS = (
        Setting("freq", "Fundamental", "text", default="", coerce=freq_text, hint="strongest", help="the fundamental, blank for the strongest peak"),
        Setting("count", "Harmonics", "int", default=5, min=2, max=20, help="up to this harmonic"),
    )

    def evaluate(self, ctx, mid, p):
        if p["freq"]:
            f0, l0 = _level_near(ctx, hz(p["freq"], ctx.cf))
        else:
            top = _strongest(ctx, 1)
            if not top:
                return Result([["-", "no peak"]])
            f0, l0 = top[0]
        if f0 == 0:
            return Result([[fmt_hz(f0), "the fundamental is at 0 Hz: no harmonics"]])
        lo, hi = ctx.edges
        rows = [[f"H1 {fmt_hz(f0)}", ctx.level_text(l0)]]
        marks = [Marker(f0, l0, "H1", self.COLOR, owner=mid)]
        total = 0.0
        for n in range(2, p["count"] + 1):
            want = n * f0
            if not lo <= want <= hi:
                rows.append([f"H{n} {fmt_hz(want)}", "outside span"])
                continue
            f, lvl = _level_near(ctx, want)
            total += 10 ** ((lvl - l0) / 10)
            rows.append([f"H{n} {fmt_hz(f)}", f"{lvl - l0:+.2f} dBc"])
            marks.append(Marker(f, lvl, f"H{n}", self.COLOR))
        values = [ctx.level_value(l0)]
        if total:
            rows.append(["THD", f"{100 * np.sqrt(total):.3g}% ({10 * np.log10(total):.2f} dBc)"])
            values.append(("THD", float(10 * np.log10(total)), "dBc"))
        return Result(rows, marks, at=(f0, l0), values=values)

@marker_kind("toi")
class TOI(MarkerKind):
    """Third order intercept from two tones and their third order products (2f1-f2, 2f2-f1)"""
    COLOR = BLUE
    PARAMS = (
        Setting("f1", "Tone 1", "text", default="", coerce=freq_text, hint="strongest", help="lower tone, blank: the two strongest peaks"),
        Setting("f2", "Tone 2", "text", default="", coerce=freq_text, hint="2nd strongest"),
    )

    def evaluate(self, ctx, mid, p):
        if p["f1"] and p["f2"]:
            tones = [_level_near(ctx, hz(p["f1"], ctx.cf)), _level_near(ctx, hz(p["f2"], ctx.cf))]
        else:
            tones = _strongest(ctx, 2)
            if len(tones) < 2:
                return Result([["-", "needs two tones"]])
        (f1, l1), (f2, l2) = sorted(tones)
        lo, hi = ctx.edges
        u = POWER_UNIT[ctx.unit]
        rows = [[f"{fmt_hz(f1)}, {fmt_hz(f2)}", f"{_power(ctx, l1):.2f}, {_power(ctx, l2):.2f} {u}"]]
        marks = [Marker(f1, l1, "T1", self.COLOR, owner=mid), Marker(f2, l2, "T2", self.COLOR)]
        ips = []
        for name, want, tone in (("IM3 low", 2*f1 - f2, l1), ("IM3 high", 2*f2 - f1, l2)):
            if not lo <= want <= hi:
                rows.append([name, "outside span"])
                continue
            f, lvl = _level_near(ctx, want)
            delta = tone - lvl
            ip = _power(ctx, tone) + delta / 2
            ips.append(ip)
            rows.append([f"{name} {fmt_hz(f)}", f"{-delta:+.2f} dBc, TOI {ip:.2f} {u}"])
            marks.append(Marker(f, lvl, name.replace("IM3 ", "I"), self.COLOR))
        if ips:
            rows.append(["TOI", f"{min(ips):.2f} {u}"])
        return Result(rows, marks, values=[("TOI", float(min(ips)), u)] if ips else [])

@marker_kind("limit")
class Limit(MarkerKind):
    """A limit line, pass / fail: the trace must stay under (upper) or over (lower) the level, over the whole span or
    a part of it. The line can be dragged up and down"""
    COLOR = RED
    PARAMS = (
        Setting("level", "Level", "number", default=-50.0, step=1, help="the limit, in the plot's unit"),
        Setting("side", "Kind", "select", default="upper", options=("upper", "lower"), help="upper: the trace must stay under it"),
        SETTING_FREQ.with_(hint="whole span", help="center of the part tested, blank for the whole span"),
        Setting("span", "Span", "text", default="", coerce=freq_text, hint="whole span", help="width of the part tested"),
    )

    def evaluate(self, ctx, mid, p):
        lo, hi = ctx.edges
        bands = []
        if p["freq"] or p["span"]:
            c, half = hz(p["freq"], ctx.cf), hz(p["span"], hi - lo) / 2
            lo, hi = max(lo, c - half), min(hi, c + half)
            bands.append(Band(lo, hi, self.COLOR, 0.06, owner=mid, edit=("freq", "span")))
        sel = (ctx.freqs >= lo) & (ctx.freqs <= hi)
        line = [Marker(0.0, p["level"], f"{mid} {p['side']}", self.COLOR, kind="hline", owner=mid, edit="level")]
        if not sel.any():
            return Result([["-", "outside span"]], line, bands)
        tr = ctx.trace[sel]
        k = int(np.argmax(tr) if p["side"] == "upper" else np.argmin(tr))
        worst, f = float(tr[k]), float(ctx.freqs[sel][k])
        margin = (p["level"] - worst) if p["side"] == "upper" else (worst - p["level"])
        ok = margin >= 0
        if not ok and bands:
            bands[0] = Band(lo, hi, self.COLOR, 0.18, owner=mid, edit=("freq", "span"))
        verdict = f"PASS, {margin:.2f} dB margin" if ok else f"FAIL by {-margin:.2f} dB"
        return Result([[fmt_hz(f), verdict]], line + [Marker(f, worst, "worst", self.COLOR)], bands, values=[("margin", float(margin), "dB")])

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
        for mid in other.items:
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
                 "fields": [s.to_dict() for s in MARKER_KINDS.get(it["kind"]).PARAMS],
                 "actions": list(MARKER_KINDS.get(it["kind"]).ACTIONS)} for mid, it in self.items.items()]

    @staticmethod
    def kinds() -> dict[str, list[dict]]:
        return {name: [s.to_dict() for s in cls.PARAMS] for name, cls in MARKER_KINDS.items()}

    def act(self, mid: str, action: str, plot, trace: np.ndarray, freqs: np.ndarray):
        """Run marker `mid`'s action on `plot`'s latest trace"""
        item = self._get(mid)
        kind = self._kind(item["kind"])
        if action not in kind.ACTIONS:
            raise ValueError(f"{item['kind']} has no action {action!r}, it has: {', '.join(kind.ACTIONS) or 'none'}")
        kind.act(Context(plot, trace, freqs), str(mid).upper(), item["params"], action)

    def evaluate(self, plot, trace: np.ndarray, freqs: np.ndarray) -> tuple[list[Marker], list[Band], Table | None, dict]:
        """Markers and bands to draw, the table, and the numbers measured ({"M1 level": (value, unit)}), for `plot`'s
        latest trace"""
        if not self.items:
            return [], [], None, {}
        ctx = Context(plot, trace, freqs)
        marks, bands, rows, values = [], [], [], {}
        for mid, it in self.items.items():
            kind = self._kind(it["kind"])
            res = kind.evaluate(ctx, mid, it["params"])
            if res.at is not None:
                ctx.found[mid] = res.at
            marks += res.marks
            bands += res.bands
            for name, v, unit in res.values:
                if np.isfinite(v):
                    values[f"{mid} {name}"] = (float(v), unit)
            for k, cells in enumerate(res.rows):
                rows.append(TableRow(mid if k == 0 else "", [mid, it["kind"], *cells] if k == 0 else ["", "", *cells]))
        return marks, bands, Table(COLUMNS, rows), values
