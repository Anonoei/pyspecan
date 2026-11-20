"""The set of live plots of a view, and how they are laid out"""
import itertools
import threading
import time
import traceback

from .base import PLOTS, Plot, default_globals
from .layout import LayoutSpec, PlotSpec, validate
from .settings import GLOBAL_SETTINGS, by_key
from .source import Source

WHERE = ("left", "right", "above", "below", "end")

class Link:
    """Plots sharing their "link" scope settings, one resolved auto ref level and one marker set"""
    def __init__(self, lid: str, values: dict, markers=None):
        self.id = lid
        self.members: list[str] = []
        self.values = values  # link scope key -> value
        self.auto = None      # the ref level "auto" resolved to, shared by the members
        self.markers = markers

def _changed(settings, values: dict) -> dict:
    """The values of `settings` that differ from their defaults"""
    return {s.key: values[s.key] for s in settings if s.key in values and values[s.key] != s.parse(s.default)}

def _marker_spec(m: dict) -> dict:
    from .markers import MARKER_KINDS  # markers import the plots
    return {"kind": m["kind"], **_changed(MARKER_KINDS.get(m["kind"]).PARAMS, m["params"])}

class PlotSet:
    """Owns plot instances by id. Views mirror it in their own widgets.

    `layout` is rows of plot ids, for views that arrange plots in a grid.
    """
    def __init__(self, source: Source, globals: dict | None = None):
        self.source = source
        self.globals = default_globals(**(globals or {}))
        self.plots: dict[str, Plot] = {}
        self.layout: list[list[str]] = []
        self.links: dict[str, Link] = {}
        self._ids = itertools.count(1)
        self._link_ids = itertools.count(1)
        self.lock = threading.RLock()

    def _new(self, name: str, **settings) -> Plot:
        return PLOTS.get(name)(self.source, globals=self.globals, **settings)

    def __iter__(self):
        return iter(list(self.plots.items()))

    def __len__(self):
        return len(self.plots)

    def get(self, pid: str) -> Plot:
        try:
            return self.plots[pid]
        except KeyError:
            raise ValueError(f"unknown plot {pid!r}") from None

    def add(self, name: str, row: int | None = None, **settings) -> str:
        """Add a plot in `row` (an existing row index), or in a new row. `settings`: its initial values"""
        PLOTS.get(name)
        with self.lock:
            pid = f"p{next(self._ids)}"
            self.plots[pid] = self._new(name, **settings)
            if row is not None and 0 <= row < len(self.layout):
                self.layout[row].append(pid)
            else:
                self.layout.append([pid])
        return pid

    def remove(self, pid: str):
        with self.lock:
            self.get(pid)
            self.unlink(pid)
            del self.plots[pid]
            self._detach(pid)

    def _detach(self, pid: str):
        """Take a plot out of the layout, rows that end up empty go away"""
        self.layout = [row for row in ([i for i in row if i != pid] for row in self.layout) if row]

    def move(self, pid: str, target: str | None, where: str):
        """Move a plot next to another one

        where: "left" / "right" put it in the target's row, "above" / "below" in a new row
        over / under the target's row, "end" (no target needed) in a new row at the bottom.
        """
        if where not in WHERE:
            raise ValueError(f"unknown place {where!r}, use {', '.join(WHERE)}")
        with self.lock:
            self.get(pid)
            if where == "end":
                self._detach(pid)
                self.layout.append([pid])
                return
            self.get(target) # type: ignore
            if pid == target:
                return
            self._detach(pid)
            r = next(i for i, row in enumerate(self.layout) if target in row)
            if where in ("left", "right"):
                self.layout[r].insert(self.layout[r].index(target) + (where == "right"), pid)
            else:
                self.layout.insert(r + (where == "below"), [pid])

    def retype(self, pid: str, name: str):
        """Replace a plot by another type, keeping its place, paused state, link (when the new type can share it)
        and markers (when the new type carries them)"""
        cls = PLOTS.get(name)
        with self.lock:
            old = self.get(pid)
            link = old.link
            peer = next((m for m in link.members if m != pid), None) if link else None
            self.unlink(pid) # leaves `old` its own copy of the link's markers
            new = self.plots[pid] = self._new(name)
            new.enabled = old.enabled
            if peer is not None and cls.LINK_DOMAIN is not None and cls.LINK_DOMAIN == self.plots[peer].LINK_DOMAIN:
                self.link(pid, peer) # the link's markers come back with it, carrying ours too would duplicate them
            elif cls.MARKERS and getattr(old, "own_markers", None) is not None:
                new.own_markers = old.own_markers

    # --- settings --- #
    def set(self, pid: str, key: str, value):
        """Change a setting of plot `pid`, every plot sharing the value (its link, or all of them for a
        global) hears of the change"""
        with self.lock:
            plot = self.get(pid)
            if key == "enabled":
                plot.set(key, value)
                return
            s = plot.setting(key)
            if s is None:
                raise ValueError(f"unknown plot setting {key!r}")
            plot.store(s)[key] = s.parse(value)
            for other in self.sharing(pid, s):
                if other.setting(key) is not None:
                    other.apply(other.setting(key))

    def sharing(self, pid: str, s) -> list[Plot]:
        """The plots that see the value of setting `s` of plot `pid`"""
        plot = self.get(pid)
        if s.scope == "global":
            return list(self.plots.values())
        if s.scope == "link" and plot.link is not None:
            return [self.plots[m] for m in plot.link.members]
        return [plot]

    def set_global(self, key: str, value):
        s = by_key(GLOBAL_SETTINGS, key)
        if s is None:
            raise ValueError(f"unknown global setting {key!r}")
        with self.lock:
            self.globals[key] = s.parse(value)
            for plot in self.plots.values():
                plot.apply(s)

    # --- links --- #
    def linkable(self, pid: str) -> list[str]:
        """Plots `pid` can be linked to"""
        dom = self.get(pid).LINK_DOMAIN
        if dom is None:
            return []
        return [o for o, p in self.plots.items() if o != pid and p.LINK_DOMAIN == dom]

    def link(self, pid: str, target: str) -> str:
        """Link `pid` to `target` (joining target's link if it has one), returns the link id.
        `pid` takes on the link's values; its markers join the shared set"""
        with self.lock:
            plot, other = self.get(pid), self.get(target)
            if pid == target:
                raise ValueError("can not link a plot to itself")
            if plot.LINK_DOMAIN is None or plot.LINK_DOMAIN != other.LINK_DOMAIN:
                raise ValueError(f"{plot.NAME} can not be linked to {other.NAME}")
            if plot.link is not None:
                if plot.link is other.link:
                    return plot.link.id
                self.unlink(pid)
            link = other.link
            if link is None:
                link = Link(f"L{next(self._link_ids)}", self._link_values(other), getattr(other, "own_markers", None))
                self.links[link.id] = link
                link.members.append(target)
                other.link = link
            for k, v in self._link_values(plot).items():
                link.values.setdefault(k, v) # a key the link lacks keeps the joining plot's value
            if link.markers is None:
                link.markers = getattr(plot, "own_markers", None)
            elif getattr(plot, "own_markers", None) is not None and plot.own_markers is not link.markers:
                link.markers.merge(plot.own_markers)
            link.members.append(pid)
            plot.link = link
            plot.reset()
            return link.id

    @staticmethod
    def _link_values(plot: Plot) -> dict:
        return {s.key: getattr(plot, s.key) for s in plot.SETTINGS if s.scope == "link"}

    def unlink(self, pid: str):
        """Take `pid` out of its link keeping the values and markers it had. A link left with one plot goes away"""
        with self.lock:
            plot = self.get(pid)
            link = plot.link
            if link is None:
                return
            self._leave(plot, link, last=False)
            link.members.remove(pid)
            if len(link.members) == 1:
                last = self.plots[link.members[0]]
                self._leave(last, link, last=True)
                link.members.clear()
            if not link.members:
                del self.links[link.id]

    @staticmethod
    def _leave(plot: Plot, link: Link, last: bool):
        for s in plot.SETTINGS:
            if s.scope == "link" and s.key in link.values:
                plot._cfg[s.key] = link.values[s.key]
        if link.markers is not None and hasattr(plot, "own_markers"):
            plot.own_markers = link.markers if last else link.markers.copy()
        if link.auto is not None and hasattr(plot, "_auto"):
            plot._auto = link.auto
        plot.link = None

    # --- layouts --- #
    def clear(self):
        """Remove every plot. Ids keep counting up, so a frame of an old plot never lands on a new one"""
        with self.lock:
            self.plots.clear()
            self.layout = []
            self.links.clear()

    def apply(self, spec: LayoutSpec):
        """Replace every plot by the ones of `spec` (see plots.layout), validate it first. Globals the
        spec leaves out go back to their defaults. Linked plots take the first member's "link" values"""
        validate(spec)
        with self.lock:
            self.clear()
            self.globals.update(default_globals(**spec.globals)) # in place, plots share the dict
            ids: list[list[str]] = []
            for r, row in enumerate(spec.rows):
                ids.append([self.add(p.type, r if r < len(self.layout) else None, **p.settings) for p in row])
            first: dict[str, str] = {} # link name -> its first plot
            for r, c, p in spec.plots():
                if p.link:
                    pid = ids[r][c]
                    if p.link in first:
                        self.link(pid, first[p.link])
                    else:
                        first[p.link] = pid
            for r, c, p in spec.plots():
                for m in p.markers:
                    self.plots[ids[r][c]].markers.add(m["kind"], **{k: v for k, v in m.items() if k != "kind"})

    def to_spec(self) -> LayoutSpec:
        """The plots as a LayoutSpec: values that differ from the defaults, links, markers"""
        with self.lock:
            names = {lid: f"link{i}" for i, lid in enumerate(self.links, 1)}
            done: set[str] = set() # links whose markers are written
            rows = []
            for row in self.layout:
                out = []
                for pid in row:
                    plot = self.plots[pid]
                    settings = _changed(plot.SETTINGS, plot.own_values())
                    markers = []
                    if plot.MARKERS and (plot.link is None or plot.link.id not in done):
                        markers = [_marker_spec(m) for m in plot.markers.describe()]
                    if plot.link is not None:
                        done.add(plot.link.id)
                    out.append(PlotSpec(plot.NAME, settings, names[plot.link.id] if plot.link is not None else None, markers))
                rows.append(out)
            defaults = default_globals()
            return LayoutSpec(rows, {k: v for k, v in self.globals.items() if v != defaults[k]})

    def reset(self):
        with self.lock:
            for plot in self.plots.values():
                plot.reset()

    def describe(self) -> dict:
        """json-serializable plots and layout, for views"""
        with self.lock:
            return {
                "layout": self.layout,
                "links": {lid: list(link.members) for lid, link in self.links.items()},
                "globals": {"fields": [s.to_dict() for s in GLOBAL_SETTINGS], "settings": dict(self.globals)},
                "plots": {pid: {
                    "name": plot.NAME, "title": plot.TITLE,
                    "fields": plot.fields(), "settings": plot.settings(), "actions": list(plot.ACTIONS),
                    "link": plot.link.id if plot.link is not None else None, "linkable": self.linkable(pid),
                    **({"markers": plot.markers.describe(), "marker_kinds": plot.markers.kinds()} if plot.MARKERS else {}),
                } for pid, plot in self.plots.items()},
            }

    def update(self, log=None) -> dict:
        """Run every plot on the source's current block, returns {pid: Frame}"""
        frames = {}
        with self.lock:
            for pid, plot in list(self.plots.items()):
                t0 = time.perf_counter()
                try:
                    frame = plot.update()
                except Exception: # one broken plot shouldn't stop the others
                    traceback.print_exc() # the logger is off by default
                    if log:
                        log.error("plot %s failed", pid)
                    continue
                if frame is not None:
                    frame.ptime = time.perf_counter() - t0
                    frames[pid] = frame
        return frames
