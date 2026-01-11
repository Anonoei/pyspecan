import tkinter as tk
import tkinter.ttk as ttk

from ...config import config, Mode

from ...backend.tk import widgets
from ...backend.mpl import theme as theme_mpl

from .panels import PanelView

from .base import View as _View

class ViewFile(_View):
    __slots__ = (
        # toolbar
        "btn_prev", "btn_next",
        "var_samp", "sld_samp",
        "var_time_cur", "lbl_time_cur",
        "var_time_tot", "lbl_time_tot",
        # control panel
        "var_file", "btn_file", "ent_file",
        "var_file_fmt", "cb_file_fmt"
    )

    def __init__(self, *args, **kwargs):
        # toolbar
        self.btn_prev: ttk.Button = None # type: ignore
        self.btn_next: ttk.Button = None # type: ignore
        self.var_samp: tk.IntVar = None # type: ignore
        self.sld_samp: widgets.Scale = None # type: ignore
        self.var_time_cur: tk.StringVar = None # type: ignore
        self.lbl_time_cur: ttk.Label = None # type: ignore
        self.var_time_tot: tk.StringVar = None # type: ignore
        self.lbl_time_tot: ttk.Label = None # type: ignore
        # control panel
        self.var_file: tk.StringVar = None # type: ignore
        self.btn_file: ttk.Button = None # type: ignore
        self.ent_file: ttk.Entry = None # type: ignore
        self.var_file_fmt: tk.StringVar = None # type: ignore
        self.cb_file_fmt: ttk.Combobox = None # type: ignore
        super().__init__(*args, **kwargs)

    def draw_tb_progress(self, parent, col=0):
        self.var_samp = tk.IntVar(parent)
        self.sld_samp = widgets.Scale(
            parent, variable=self.var_samp, length=150
        )
        self.sld_samp.grid(row=0,rowspan=2,column=col, sticky=tk.NSEW)
        col += 1
        self.var_time_cur = tk.StringVar(parent)
        self.var_time_tot = tk.StringVar(parent)
        self.lbl_time_cur = ttk.Label(parent, textvariable=self.var_time_cur)
        self.lbl_time_cur.grid(row=0,column=col)
        self.lbl_time_tot = ttk.Label(parent, textvariable=self.var_time_tot)
        self.lbl_time_tot.grid(row=1,column=col)
        col += 1
        ttk.Separator(parent, orient=tk.VERTICAL).grid(row=0,rowspan=2,column=col, padx=5, sticky=tk.NS)
        col += 1
        return col

    def draw_tb_btn(self, parent, col=0):
        self.btn_prev = ttk.Button(parent, text="Prev")
        self.btn_prev.grid(row=0,rowspan=2,column=col, padx=2,pady=2)
        col += 1
        self.btn_next = ttk.Button(parent, text="Next")
        self.btn_next.grid(row=0,rowspan=2,column=col, padx=2,pady=2)
        col += 1
        return super().draw_tb_btn(parent, col)

    def draw_ctrl_sink(self, parent):
        root = ttk.Frame(parent) # Sink.FILE
        root.columnconfigure(2, weight=1)
        row = 0
        self.var_file = tk.StringVar(root)
        self.btn_file = ttk.Button(root, text="File")
        self.btn_file.grid(row=row,column=0, sticky=tk.W)
        self.ent_file = ttk.Entry(root, textvariable=self.var_file, state=tk.DISABLED, width=10)
        self.ent_file.grid(row=row,column=1,columnspan=2, sticky=tk.NSEW)
        row += 1
        ttk.Label(root, text="Format:").grid(row=row,column=0,sticky=tk.W)
        self.var_file_fmt = tk.StringVar(root)
        self.cb_file_fmt = ttk.Combobox(root, textvariable=self.var_file_fmt, width=5)
        self.cb_file_fmt.grid(row=row,column=1, sticky=tk.W)
        root.pack(padx=2,pady=2, fill=tk.X)
