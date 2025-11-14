import tkinter as tk
from tkinter import ttk

class PanelView:
    def __init__(self, master):
        self.master = master
        self.main = ttk.PanedWindow(master, orient=tk.VERTICAL)
        self.main.pack(fill=tk.BOTH, expand=True)

        self.btn_row = ttk.Button(master, text="+ ROW", style="AddRow.TButton")
        self.btn_row.place(relx=1,rely=0, x=-100, anchor=tk.NE, bordermode=tk.OUTSIDE, height=30, width=60)

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

        self.btn_col = ttk.Button(master, text="+ COL", style="AddCol.TButton")
        self.btn_col.place(relx=1,rely=0, x=-40, y=0, anchor=tk.NE, bordermode=tk.OUTSIDE, height=30, width=60)
        self.btn_close = ttk.Button(master, text="X", style="Close.TButton")
        self.btn_close.place(relx=1, rely=0, anchor=tk.NE, bordermode=tk.OUTSIDE, height=30, width=30)

    def update_layout(self):
        self.main.update_idletasks()
        self.master.update_idletasks()

class Panel:
    def __init__(self, parent, master):
        self.parent = parent
        self.master = master
        self.root = ttk.Frame(master)
        self.root.pack(fill=tk.BOTH, expand=True)

        self.wgts = {}
        self.sets = {}

        self.fr_sets = ttk.Frame(self.root, borderwidth=1, relief=tk.RAISED)
        self.fr_sets.pack(side=tk.LEFT, fill=tk.Y)

        self.lbl_sets = ttk.Label(self.fr_sets, text="Settings")
        self.lbl_sets.pack(side=tk.TOP, fill=tk.X)

        self.var_view = tk.StringVar(self.fr_sets)
        self.cb_view = ttk.Combobox(self.fr_sets, textvariable=self.var_view, width=20)
        self.cb_view.pack()
        ttk.Separator(self.fr_sets, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)

        self.settings = ttk.Frame(self.fr_sets)
        self.settings.pack(side=tk.TOP, fill=tk.BOTH)
        self.fr_sets.pack_forget()

        self.fr_main = ttk.Frame(self.root)
        self.fr_main.pack(fill=tk.BOTH, expand=True)

        self.btn_toggle = ttk.Button(master, text="Settings", style="Settings.TButton")
        self.btn_toggle.place(relx=0,rely=1, x=-5, y=5, anchor=tk.SW)
        self.btn_close = ttk.Button(master, text="X", style="Close.TButton")
        self.btn_close.place(relx=1, rely=0, y=5, anchor=tk.NE, bordermode=tk.OUTSIDE, height=30, width=30)
