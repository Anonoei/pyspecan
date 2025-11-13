import tkinter as tk
from tkinter import ttk

class PanelManager:
    def __init__(self, master):
        self.master = master
        self.main = ttk.PanedWindow(master, orient=tk.VERTICAL)
        self.main.pack(fill=tk.BOTH, expand=True)
        self.panes = []

        self.btn_row = tk.Button(master, text="Add Row", command=lambda: self.add_row())
        self.btn_row.pack(side=tk.LEFT, padx=5)

        self.add_row()

    def add_row(self):
        frame = ttk.LabelFrame(self.main, text=f"Row {len(self.panes)}")
        pane = PanelChild(self, frame)
        self.main.add(frame, weight=1)
        self.panes.append(pane)
        btn_close = ttk.Button(frame, text="X", command=lambda p=pane: self.close(p), width=2)
        btn_close.place(relx=1, rely=0, anchor=tk.NE, bordermode="outside")

        self.update_layout()

    def close(self, pane):
        idx = self.panes.index(pane)
        self.main.remove(pane.master)
        self.panes.pop(idx).root.destroy()

    def update_layout(self):
        self.main.update_idletasks()
        self.master.update_idletasks()

class PanelChild:
    def __init__(self, parent, master):
        self.parent = parent
        self.master = master
        self.root = ttk.Frame(master)
        self.root.pack(fill=tk.BOTH, expand=True)
        self.main = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main.pack(fill=tk.BOTH, expand=True)
        self.panes = []

        self.btn_col = ttk.Button(self.root, text="Add Column", command=lambda: self.add_col())
        self.btn_col.pack(side=tk.LEFT, padx=5)

        self.add_col()

    def add_col(self):
        frame = ttk.LabelFrame(self.main, text=f"Col {len(self.panes)}")
        pane = Panel(self, frame)
        self.panes.append(pane)
        self.main.add(frame, weight=1)
        #ttk.Label(self.panes[-1].main, text=f"Row {len(self.parent.panes)}, Col {len(self.panes)}").pack()

        btn_close = ttk.Button(frame, text="X", command=lambda p=pane: self.close(p), width=2)
        btn_close.place(relx=1, rely=0, anchor=tk.NE, border=tk.OUTSIDE)

        self.update_layout()

    def close(self, pane):
        idx = self.panes.index(pane)
        self.main.remove(pane.master)
        self.panes.pop(idx).root.destroy()

    def update_layout(self):
        self.main.update_idletasks()
        self.master.update_idletasks()

class Panel:
    def __init__(self, parent, master):
        self.parent = parent
        self.master = master
        self.root = ttk.Frame(master)
        self.root.pack(fill=tk.BOTH, expand=True)
        self.main = ttk.Frame(self.root)
        self.main.pack(fill=tk.BOTH, expand=True)

        self.btn_settings = ttk.Button(self.main, text="Settings", command=self.settings)
        self.btn_settings.place(relx=1,rely=1, anchor=tk.SE)

    def settings(self):
        pass


# Example usage
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Panel Manager Demo")
    panel_manager = PanelManager(root)
    root.mainloop()
