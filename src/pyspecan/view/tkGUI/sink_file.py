import tkinter as tk
import tkinter.ttk as ttk

from ...backend.tk import widgets

from ...utils import args
from .sink import Sink, args_sink

def args_file(parser):
    sink = args.get_group(parser, "Sink (FILE)")
    args_sink(sink)

class SinkFile(Sink):
    __slots__ = (
        # toolbar
        "tb_btn_prev", "tb_btn_next",
        "tb_var_samp", "tb_sld_samp",
        "tb_var_time_cur", "tb_lbl_time_cur",
        "tb_var_time_tot", "tb_lbl_time_tot",
        # control panel
        "cl_var_file", "cl_btn_file", "cl_ent_file",
        "cl_var_file_fmt", "cl_cb_file_fmt"
    )
    def __init__(self, view, **kwargs):
        super().__init__(view, **kwargs)
        # toolbar
        self.tb_btn_prev: ttk.Button = None # type: ignore
        self.tb_btn_next: ttk.Button = None # type: ignore
        self.tb_var_samp: tk.IntVar = None # type: ignore
        self.tb_sld_samp: widgets.Scale = None # type: ignore
        self.tb_var_time_cur: tk.StringVar = None # type: ignore
        self.tb_lbl_time_cur: ttk.Label = None # type: ignore
        self.tb_var_time_tot: tk.StringVar = None # type: ignore
        self.tb_lbl_time_tot: ttk.Label = None # type: ignore
        # control panel
        self.cl_var_file: tk.StringVar = None # type: ignore
        self.cl_btn_file: ttk.Button = None # type: ignore
        self.cl_ent_file: ttk.Entry = None # type: ignore
        self.cl_var_file_fmt: tk.StringVar = None # type: ignore
        self.cl_cb_file_fmt: ttk.Combobox = None # type: ignore

    def draw_tb(self, parent, col=0):
        self.tb_var_samp = tk.IntVar(parent)
        self.tb_sld_samp = widgets.Scale(
            parent, variable=self.tb_var_samp, length=150
        )
        self.tb_sld_samp.grid(row=0,rowspan=2,column=col, sticky=tk.NSEW)
        col += 1
        self.tb_var_time_cur = tk.StringVar(parent)
        self.tb_var_time_tot = tk.StringVar(parent)
        self.tb_lbl_time_cur = ttk.Label(parent, textvariable=self.tb_var_time_cur)
        self.tb_lbl_time_cur.grid(row=0,column=col)
        self.tb_lbl_time_tot = ttk.Label(parent, textvariable=self.tb_var_time_tot)
        self.tb_lbl_time_tot.grid(row=1,column=col)
        col += 1
        return col
    def draw_cl(self, parent, row=0):
        self.cl_var_file = tk.StringVar(parent)
        self.cl_btn_file = ttk.Button(parent, text="File")
        self.cl_btn_file.grid(row=row,column=0, sticky=tk.W)
        self.cl_ent_file = ttk.Entry(parent, textvariable=self.cl_var_file, state=tk.DISABLED, width=10)
        self.cl_ent_file.grid(row=row,column=1,columnspan=2, sticky=tk.NSEW)
        row += 1
        ttk.Label(parent, text="Format:").grid(row=row,column=0,sticky=tk.W)
        self.cl_var_file_fmt = tk.StringVar(parent)
        self.cl_cb_file_fmt = ttk.Combobox(parent, textvariable=self.cl_var_file_fmt, width=5)
        self.cl_cb_file_fmt.grid(row=row,column=1, sticky=tk.W)
        parent.columnconfigure(2, weight=1)
        return row

    def finish_tb(self):
        row, col = self.view.tb_fr_btn.grid_size()
        col += 1
        self.tb_btn_prev = ttk.Button(self.view.tb_fr_btn, text="Prev")
        self.tb_btn_prev.grid(row=0,rowspan=2,column=col, padx=2)
        col += 1
        self.tb_btn_next = ttk.Button(self.view.tb_fr_btn, text="Next")
        self.tb_btn_next.grid(row=0,rowspan=2,column=col, padx=2)
