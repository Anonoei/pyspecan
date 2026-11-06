import tkinter as tk
from tkinter import ttk

class PanelView:
    """The area plots live in: rows (top to bottom) of panes (left to right)"""
    def __init__(self, master):
        self.master = master
        self.main = ttk.PanedWindow(master, orient=tk.VERTICAL)
        self.main.pack(fill=tk.BOTH, expand=True)

    def update_layout(self):
        self.main.update_idletasks()
        self.master.update_idletasks()

class PanelChild:
    """A row of panes"""
    def __init__(self, parent, master):
        self.parent = parent
        self.master = master
        self.root = ttk.Frame(master)
        self.root.pack(fill=tk.BOTH, expand=True)
        self.main = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main.pack(fill=tk.BOTH, expand=True)

    def update_layout(self):
        self.main.update_idletasks()
        self.master.update_idletasks()

class Panel:
    """One plot: a settings column and the drawing area"""
    def __init__(self, parent, master):
        self.parent = parent
        self.master = master
        self.root = ttk.Frame(master)
        self.root.pack(fill=tk.BOTH, expand=True)

        self.fr_sets = ttk.Frame(self.root, borderwidth=1, relief=tk.RAISED)
        self.fr_sets.pack(side=tk.LEFT, fill=tk.Y)

        self.lbl_sets = ttk.Label(self.fr_sets, text="Settings")
        self.lbl_sets.pack(side=tk.TOP, fill=tk.X)
        ttk.Separator(self.fr_sets, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)

        self.settings = ttk.Frame(self.fr_sets)
        self.settings.pack(side=tk.TOP, fill=tk.BOTH)

        self.fr_main = ttk.Frame(self.root)
        self.fr_main.pack(fill=tk.BOTH, expand=True)

        self.lbl_grip = ttk.Label(master, text="⠿ drag", style="Time.TLabel", cursor="fleur")
        self.lbl_grip.place(relx=0.5, rely=0, y=5, anchor=tk.N, bordermode=tk.OUTSIDE, height=20)
        self.btn_toggle = ttk.Button(master, text="Settings", style="Settings.TButton")
        self.btn_toggle.place(relx=0,rely=1, x=-5, y=5, anchor=tk.SW)
        self.btn_close = ttk.Button(master, text="X", style="Close.TButton")
        self.btn_close.place(relx=1, rely=0, y=5, anchor=tk.NE, bordermode=tk.OUTSIDE, height=30, width=30)
