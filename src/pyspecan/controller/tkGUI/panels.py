import tkinter as tk
from tkinter import ttk

from ...view.tkGUI.panels import PanelView, PanelChild, Panel

class PanelController:
    def __init__(self, parent, panel: PanelView):
        self.parent = parent
        self.panel = panel
        self.rows = []
        self.cols = {}
        self.view = {}

        self.panel.btn_row.configure(command=self.add_row)
        self.add_row()

    def add_row(self):
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
        raise NotImplementedError

    def set_view(self, e, child: PanelChild, pane: Panel):
        raise NotImplementedError

    def reset(self):
        pass

    def get_pane(self, child: PanelChild, pane: Panel):
        return self.cols[child][self.cols[child].index(pane)]

    def get_view(self, child: PanelChild, pane: Panel):
        return self.view[child][pane]
