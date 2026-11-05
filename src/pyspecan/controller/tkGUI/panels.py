"""Rows and columns of plot panes, each pane shows one plot of the controller's PlotSet"""
import tkinter as tk
from tkinter import ttk

from ... import logger
from ...view.tkGUI.panels import PanelView, PanelChild, Panel

from .plot import PlotPane

class PanelController:
    def __init__(self, ctrl, panel: PanelView):
        self.log = logger.new("tkGUI.Panels")
        self.ctrl = ctrl
        self.panel = panel
        self.rows: list[PanelChild] = []
        self.cols: dict[PanelChild, list[Panel]] = {}
        self.view: dict[PanelChild, dict[Panel, PlotPane | None]] = {}

        self.panel.btn_row.configure(command=self.add_row)
        self.add_row()

    def panes(self) -> list[PlotPane]:
        return [p for views in self.view.values() for p in views.values() if p is not None]

    # --- layout --- #
    def add_row(self):
        if len(self.rows) > 5:
            return
        frame = ttk.LabelFrame(self.panel.main, text=f"Row {len(self.rows)}")
        child = PanelChild(self, frame)
        self.rows.append(child)
        self.cols[child] = []
        self.view[child] = {}

        self.panel.main.add(frame, weight=1)

        child.btn_close.configure(command=lambda c=child: self.del_row(c))
        child.btn_col.configure(command=lambda c=child: self.add_col(c))

        self.add_col(child)
        self.panel.update_layout()

    def del_row(self, child: PanelChild):
        for pane in list(self.cols[child]):
            self._drop_plot(child, pane)
        idx = self.rows.index(child)
        del self.cols[child], self.view[child]
        self.panel.main.remove(child.master)
        self.rows.pop(idx).master.destroy()

    def add_col(self, child: PanelChild):
        if len(self.cols[child]) > 5:
            return
        frame = ttk.LabelFrame(child.main, text=f"Col {len(self.cols[child])}")
        pane = Panel(self, frame)
        self.cols[child].append(pane)
        self.view[child][pane] = None

        child.main.add(frame, weight=1)

        pane.btn_close.configure(command=lambda c=child, p=pane: self.del_col(c, p))
        pane.btn_toggle.configure(command=lambda c=child, p=pane: self.toggle_settings(c, p))
        self.toggle_settings(child, pane)

        pane.cb_view.config(values=self.ctrl.plot_types)
        pane.cb_view.bind("<<ComboboxSelected>>", lambda e, c=child, p=pane: self.set_view(c, p))
        child.update_layout()

    def del_col(self, child: PanelChild, pane: Panel):
        self._drop_plot(child, pane)
        idx = self.cols[child].index(pane)
        child.main.remove(pane.master)
        del self.view[child][pane]
        self.cols[child].pop(idx).master.destroy()
        if len(self.cols[child]) == 0:
            self.del_row(child)

    def toggle_settings(self, child: PanelChild, pane: Panel):
        """Toggle settings panel visibility"""
        if pane.fr_sets.winfo_ismapped():
            pane.fr_sets.forget()
        else:
            pane.fr_sets.pack(side=tk.LEFT, fill=tk.Y, before=pane.fr_main)

    # --- plots --- #
    def _drop_plot(self, child: PanelChild, pane: Panel):
        shown = self.view[child].get(pane)
        if shown is not None:
            self.view[child][pane] = None
            shown.destroy()
            self.ctrl.del_plot(shown.pid)

    def set_view(self, child: PanelChild, pane: Panel, name: str | None = None):
        """Show plot `name` (default: the pane's combobox) in the pane"""
        name = name or pane.var_view.get()
        if name not in self.ctrl.plot_types:
            return
        pane.var_view.set(name)
        self._drop_plot(child, pane)
        pid = self.ctrl.add_plot(name)
        self.view[child][pane] = PlotPane(self.ctrl, pane, pid)

    # --- drawing --- #
    def push(self, frames: dict):
        for pane in self.panes():
            if pane.pid in frames:
                pane.push(frames[pane.pid])

    def render(self):
        for pane in self.panes():
            if not self.ctrl.running: # the window is closing
                return
            pane.render()

    def on_reset(self):
        for pane in self.panes():
            pane.reset()
