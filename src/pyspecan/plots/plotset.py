"""The set of live plots of a view, and how they are laid out"""
import itertools
import threading
import time
import traceback

from .base import PLOTS, Plot
from .source import Source

WHERE = ("left", "right", "above", "below", "end")

class PlotSet:
    """Owns plot instances by id. Views mirror it in their own widgets.

    `layout` is rows of plot ids, for views that arrange plots in a grid.
    """
    def __init__(self, source: Source, **plot_args):
        self.source = source
        self.plot_args = plot_args # initial setting values given to every new plot
        self.plots: dict[str, Plot] = {}
        self.layout: list[list[str]] = []
        self._ids = itertools.count(1)
        self.lock = threading.RLock()

    def __iter__(self):
        return iter(list(self.plots.items()))

    def __len__(self):
        return len(self.plots)

    def get(self, pid: str) -> Plot:
        try:
            return self.plots[pid]
        except KeyError:
            raise ValueError(f"unknown plot {pid!r}") from None

    def add(self, name: str, row: int | None = None) -> str:
        """Add a plot in `row` (an existing row index), or in a new row"""
        cls = PLOTS.get(name)
        with self.lock:
            pid = f"p{next(self._ids)}"
            self.plots[pid] = cls(self.source, **self.plot_args)
            if row is not None and 0 <= row < len(self.layout):
                self.layout[row].append(pid)
            else:
                self.layout.append([pid])
        return pid

    def remove(self, pid: str):
        with self.lock:
            self.get(pid)
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
        """Replace a plot by another type, keeping its place and paused state"""
        cls = PLOTS.get(name)
        with self.lock:
            enabled = self.get(pid).enabled
            self.plots[pid] = cls(self.source, **self.plot_args)
            self.plots[pid].enabled = enabled

    def reset(self):
        with self.lock:
            for plot in self.plots.values():
                plot.reset()

    def describe(self) -> dict:
        """json-serializable plots and layout, for views"""
        with self.lock:
            return {
                "layout": self.layout,
                "plots": {pid: {
                    "name": plot.NAME, "title": plot.TITLE,
                    "fields": plot.fields(), "settings": plot.settings(),
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
