import tkinter as tk
import tkinter.ttk as ttk

from ...backend.tk import widgets

from ...utils import args
from .sink import Sink, args_sink

def args_live(parser):
    sink = args.get_group(parser, "Sink (LIVE)")
    args_sink(sink)

class SinkLive(Sink):
    __slots__ = (
        # control panel
        "cl_var_dev", "cl_cb_dev",
        "cl_fr_rx_rf", "cl_var_rx_rf", "cl_ent_rx_rf",
        "cl_fr_rx_if", "cl_var_rx_if", "cl_ent_rx_if",
        "cl_fr_rx_bb", "cl_var_rx_bb", "cl_ent_rx_bb"
    )
    def __init__(self, view, **kwargs):
        super().__init__(view, **kwargs)
        self.cl_var_dev: tk.StringVar = None # type: ignore
        self.cl_cb_dev: ttk.Combobox = None # type: ignore
        self.cl_fr_rx_rf: ttk.Frame = None # type: ignore
        self.cl_var_rx_rf: tk.StringVar = None # type: ignore
        self.cl_ent_rx_rf: ttk.Entry = None # type: ignore
        self.cl_fr_rx_if: ttk.Frame = None # type: ignore
        self.cl_var_rx_if: tk.StringVar = None # type: ignore
        self.cl_ent_rx_if: ttk.Entry = None # type: ignore
        self.cl_fr_rx_bb: ttk.Frame = None # type: ignore
        self.cl_var_rx_bb: tk.StringVar = None # type: ignore
        self.cl_ent_rx_bb: ttk.Entry = None # type: ignore

    def draw_cl(self, parent, row=0):
        parent.columnconfigure(1, weight=1)
        self.cl_var_dev = tk.StringVar(parent) # TODO: switch from ent to combo
        ttk.Label(parent, text="Device:").grid(row=row,column=0, sticky=tk.W)
        self.cl_cb_dev = ttk.Combobox(parent, textvariable=self.cl_var_dev, width=20)
        # self.ent_dev = ttk.Entry(root, textvariable=self.var_dev, state=tk.DISABLED, width=10)
        self.cl_cb_dev.grid(row=row,column=1, sticky=tk.NSEW)
        row += 1
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=2, pady=5, sticky=tk.EW)
        row += 1
        self.cl_fr_rx_rf = ttk.Frame(parent)
        self.cl_fr_rx_rf.columnconfigure(1, weight=1)
        self.cl_var_rx_rf = tk.StringVar(self.cl_fr_rx_rf)
        ttk.Label(self.cl_fr_rx_rf, text="Rx RF Gain:").grid(row=0,column=0, sticky=tk.W)
        self.cl_ent_rx_rf = ttk.Entry(self.cl_fr_rx_rf, textvariable=self.cl_var_rx_rf, width=3)
        self.cl_ent_rx_rf.grid(row=0,column=1, sticky=tk.E)
        self.cl_fr_rx_rf.grid(row=row,column=0,columnspan=2, sticky=tk.NSEW)
        # root.columnconfigure(row, weight=1)
        row += 1
        self.cl_fr_rx_if = ttk.Frame(parent)
        self.cl_fr_rx_if.columnconfigure(1, weight=1)
        self.cl_var_rx_if = tk.StringVar(self.cl_fr_rx_if)
        ttk.Label(self.cl_fr_rx_if, text="Rx IF Gain:").grid(row=0,column=0, sticky=tk.W)
        self.cl_ent_rx_if = ttk.Entry(self.cl_fr_rx_if, textvariable=self.cl_var_rx_if, width=3)
        self.cl_ent_rx_if.grid(row=0,column=1, sticky=tk.E)
        self.cl_fr_rx_if.grid(row=row,column=0,columnspan=2, sticky=tk.NSEW)
        # root.columnconfigure(row, weight=1)
        row += 1
        self.cl_fr_rx_bb = ttk.Frame(parent)
        self.cl_fr_rx_bb.columnconfigure(1, weight=1)
        self.cl_var_rx_bb = tk.StringVar(self.cl_fr_rx_bb)
        ttk.Label(self.cl_fr_rx_bb, text="Rx BB Gain:").grid(row=0,column=0, sticky=tk.W)
        self.cl_ent_rx_bb = ttk.Entry(self.cl_fr_rx_bb, textvariable=self.cl_var_rx_bb, width=3)
        self.cl_ent_rx_bb.grid(row=0,column=1, sticky=tk.E)
        self.cl_fr_rx_bb.grid(row=row,column=0,columnspan=2, sticky=tk.NSEW)
        # root.columnconfigure(row, weight=1)
        return row
