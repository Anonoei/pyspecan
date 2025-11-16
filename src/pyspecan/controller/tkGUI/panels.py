import tkinter as tk
from tkinter import ttk

from ...view.tkGUI.panels import PanelView, PanelChild, Panel

from .plot_base import TimePlotController, FreqPlotController, BlitPlot
from .dispatch import CMD

class PanelController:
    def __init__(self, parent, panel: PanelView, plots):
        self.parent = parent
        self.panel = panel
        self.rows = []
        self.cols = {}
        self.view = {}
        self.active = []
        self.plots = plots

        self.panel.btn_row.configure(command=self.add_row)
        self.add_row()

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
        idx = self.rows.index(child)
        del self.cols[child]
        self.panel.main.remove(child.master)
        self.rows.pop(idx).root.destroy()

    def add_col(self, child: PanelChild):
        if len(self.cols[child]) > 5:
            return
        frame = ttk.LabelFrame(child.main, text=f"Col {len(self.cols[child])}")
        pane = Panel(self, frame)
        self.cols[child].append(pane)
        self.view[child][pane] = None

        child.main.add(frame, weight=1)
        #ttk.Label(self.panes[-1].main, text=f"Row {len(self.parent.panes)}, Col {len(self.panes)}").pack()

        pane.btn_close.configure(command=lambda c=child, p=pane: self.del_col(c,p))
        pane.btn_toggle.configure(command=lambda c=child, p=pane: self.toggle_settings(c,p))
        self.toggle_settings(child, pane)

        self.set_settings(child, pane)
        child.update_layout()

    def del_col(self, child: PanelChild, pane: Panel):
        idx = self.cols[child].index(pane)
        child.main.remove(pane.master)
        plot = self.view[child][pane]
        if plot is not None:
            self.active.pop(self.active.index(plot))
        del self.view[child][pane]
        self.cols[child].pop(idx).root.destroy()
        if len(self.cols[child]) == 0:
            self.del_row(child)

    def toggle_settings(self, child: PanelChild, pane: Panel):
        """Toggle settings panel visibility"""
        if pane.fr_sets.winfo_ismapped():
            pane.fr_sets.forget()
            # self.btn_toggle.config(text="Show Settings")
        else:
            pane.fr_sets.pack(side=tk.LEFT, fill=tk.Y, before=pane.fr_main)
            # self.btn_toggle.config(text="Hide Settings")

    def set_settings(self, child: PanelChild, pane: Panel):
        pane.cb_view.config(values=list(k for k in self.plots.keys()))
        pane.cb_view.bind("<<ComboboxSelected>>", lambda e,c=child, p=pane: self.set_view(e,c,p))

    def set_view(self, e, child: PanelChild, pane: Panel):
        view = pane.var_view.get()
        if view in self.plots:
            if self.view[child][pane] is not None:
                pane.wgts = {}
                pane.sets = {}
                for ch in pane.fr_main.winfo_children():
                    ch.destroy()
                for ch in pane.settings.winfo_children():
                    ch.destroy()
                self.del_active(child, pane, self.view[child][pane])
            plot = self.plots[view](self.parent, pane)
            self.view[child][pane] = plot
            self.add_active(child, pane, plot)

    def get_pane(self, child: PanelChild, pane: Panel):
        return self.cols[child][self.cols[child].index(pane)]

    def get_view(self, child: PanelChild, pane: Panel):
        return self.view[child][pane]

    def add_active(self, child, pane, plot):
        self.active.append(plot)

    def del_active(self, child, pane, plot):
        plot.enabled = False
        self.active.pop(self.active.index(plot))

    def on_plot(self, model):
        if len(self.active) == 0:
            self.parent.dispatch.queue.put(CMD.STOP)
        for view in self.active:
            if not isinstance(view.plotter, BlitPlot):
                view.plotter.cla()
                print("Cleared plot!")
            view.plot(model.samples)

    def on_update_f(self, f):
        for view in self.active:
            if isinstance(view, FreqPlotController):
                view.update_f(f)

    def on_update_nfft(self, nfft):
        for view in self.active:
            if isinstance(view, FreqPlotController):
                view.update_nfft(nfft)

    def on_update_fs(self, Fs):
        for view in self.active:
            view.update_fs(Fs)

    def on_reset(self):
        for view in self.active:
            view.reset()
