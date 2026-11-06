"""Rows and columns of plot panes

The controller's PlotSet layout (rows of plot ids) is the source of truth. The widgets are
rebuilt from it after every change: tk cannot move a widget to another parent, so dragging a plot
to a new place means re-creating the panes. What a plot must keep across that lives in `keep`.
"""
import tkinter as tk
from tkinter import ttk

from ... import logger
from ...view.tkGUI.panels import PanelView, PanelChild, Panel

from .plot import PlotPane

BAR = 10 # [px] thickness of the drop indicator

class PanelController:
    def __init__(self, ctrl, panel: PanelView):
        self.log = logger.new("tkGUI.Panels")
        self.ctrl = ctrl
        self.panel = panel
        self.rows: list[PanelChild] = []
        self.panes: dict[str, PlotPane] = {}
        self.frames: dict[tk.Misc, str] = {} # pane frame -> plot id, to find what is under the pointer
        self.keep: dict[str, dict] = {}      # plot id -> what survives a rebuild
        self.drag: dict | None = None
        self.overlay = tk.Frame(panel.master, background="#5b9bd5")

    # --- structure --- #
    def add(self, name: str) -> str:
        """Add a plot in a new row at the bottom"""
        pid = self.ctrl.add_plot(name)
        self.rebuild()
        return pid

    def remove(self, pid: str):
        self.ctrl.del_plot(pid)
        self.keep.pop(pid, None)
        self.rebuild()

    def move(self, pid: str, target: str, where: str):
        self.ctrl.move_plot(pid, target, where)
        self.rebuild()

    def rebuild(self):
        """Create the widgets for the layout"""
        for pane in self.panes.values():
            pane.close()
        for row in self.rows:
            row.master.destroy()
        self.rows, self.panes, self.frames = [], {}, {}
        for r, ids in enumerate(self.ctrl.plots.layout):
            frame = ttk.LabelFrame(self.panel.main, text=f"Row {r}")
            row = PanelChild(self, frame)
            self.rows.append(row)
            self.panel.main.add(frame, weight=1)
            for pid in ids:
                self._add_pane(row, pid)
            row.update_layout()
        self.panel.update_layout()
        self.ctrl.view.root.update_idletasks()

    def _add_pane(self, row: PanelChild, pid: str):
        frame = ttk.LabelFrame(row.main)
        pane = Panel(self, frame)
        row.main.add(frame, weight=1)
        keep = self.keep.setdefault(pid, {"settings_open": True})
        if not keep["settings_open"]:
            pane.fr_sets.forget()
        pane.btn_close.configure(command=lambda: self.ctrl.when_idle(lambda: self.remove(pid)))
        pane.btn_toggle.configure(command=lambda: self.toggle_settings(pid))
        for widget in (pane.lbl_grip, frame):
            widget.bind("<ButtonPress-1>", lambda e, pid=pid: self._drag_start(pid))
            widget.bind("<B1-Motion>", self._drag_move)
            widget.bind("<ButtonRelease-1>", self._drag_end)
        self.frames[frame] = pid
        self.panes[pid] = PlotPane(self.ctrl, pane, pid, keep)

    def toggle_settings(self, pid: str):
        pane = self.panes[pid].pane
        if pane.fr_sets.winfo_ismapped():
            pane.fr_sets.forget()
        else:
            pane.fr_sets.pack(side=tk.LEFT, fill=tk.Y, before=pane.fr_main)
        self.keep[pid]["settings_open"] = bool(pane.fr_sets.winfo_manager())

    # --- drag & drop --- #
    def _drag_start(self, pid: str):
        self.drag = {"pid": pid, "drop": None}

    def drop_target(self, x: int, y: int):
        """(plot id, where) for the pointer at root coordinates, None if it isn't over another plot"""
        widget = self.ctrl.view.root.winfo_containing(x, y)
        while widget is not None and widget not in self.frames:
            widget = widget.master
        if widget is None or self.drag is None or self.frames[widget] == self.drag["pid"]:
            return None
        w, h = max(widget.winfo_width(), 1), max(widget.winfo_height(), 1)
        fx, fy = (x - widget.winfo_rootx()) / w, (y - widget.winfo_rooty()) / h
        edges = {"left": fx, "right": 1 - fx, "above": fy, "below": 1 - fy}
        return self.frames[widget], min(edges, key=edges.get), widget # the nearest edge

    def _drag_move(self, event):
        if self.drag is None:
            return
        self.ctrl.view.root.configure(cursor="fleur")
        target = self.drop_target(event.x_root, event.y_root)
        self.drag["drop"] = target
        if target is None:
            self.overlay.place_forget()
            return
        _, where, frame = target # an opaque bar on the edge the plot will go to, tk widgets can't be see-through
        bar = {
            "left": dict(relx=0, rely=0, relheight=1, width=BAR, anchor=tk.NW),
            "right": dict(relx=1, rely=0, relheight=1, width=BAR, anchor=tk.NE),
            "above": dict(relx=0, rely=0, relwidth=1, height=BAR, anchor=tk.NW),
            "below": dict(relx=0, rely=1, relwidth=1, height=BAR, anchor=tk.SW),
        }[where]
        self.overlay.place(in_=frame, **bar)
        self.overlay.lift()

    def _drag_end(self, event):
        drag, self.drag = self.drag, None
        self.overlay.place_forget()
        self.ctrl.view.root.configure(cursor="")
        if drag is not None and drag["drop"] is not None: # the last place the pointer was over
            pid, (tid, where, _) = drag["pid"], drag["drop"]
            self.ctrl.when_idle(lambda: self.move(pid, tid, where)) # not from inside the widget's own event

    # --- drawing --- #
    def push(self, frames: dict):
        for pid, pane in self.panes.items():
            if pid in frames:
                pane.push(frames[pid])

    def render(self):
        for pane in list(self.panes.values()):
            if not self.ctrl.running: # the window is closing
                return
            pane.render()

    def on_reset(self):
        for pane in self.panes.values():
            pane.reset()
