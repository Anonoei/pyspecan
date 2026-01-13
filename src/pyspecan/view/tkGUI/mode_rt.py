import tkinter as tk
import tkinter.ttk as ttk

from ...backend.tk import widgets

from ...utils import args
from .mode import Mode, args_mode

def args_rt(parser):
    mode = args.get_group(parser, "Mode (RT)")
    args_mode(mode)

class ModeRT(Mode):
    __slots__ = (
        # control panel
        "cl_var_overlap", "cl_ent_overlap"
    )
    def __init__(self, view, **kwargs):
        super().__init__(view, **kwargs)
        self.cl_var_overlap: tk.StringVar = None # type: ignore
        self.cl_ent_overlap: ttk.Entry = None # type: ignore

    def draw_tb(self, parent, col=0):
        return col
    def draw_cl(self, parent, row=0):
        self.cl_var_overlap = tk.StringVar(parent)
        ttk.Label(parent, text="Overlap:").grid(row=row,column=0)
        self.cl_ent_overlap = ttk.Entry(parent, textvariable=self.cl_var_overlap, width=4)
        self.cl_ent_overlap.grid(row=row,column=1, sticky=tk.NSEW)
        row += 1
        return row
