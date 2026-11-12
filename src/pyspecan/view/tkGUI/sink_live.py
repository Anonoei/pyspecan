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
        "cl_var_rx", "cl_ent_rx",
        "cl_fr_stages", "cl_stage_vars", "cl_stage_ents"
    )
    def __init__(self, view, **kwargs):
        super().__init__(view, **kwargs)
        self.cl_var_dev: tk.StringVar = None # type: ignore
        self.cl_cb_dev: ttk.Combobox = None # type: ignore
        self.cl_var_rx: tk.StringVar = None # type: ignore
        self.cl_ent_rx: ttk.Entry = None # type: ignore
        self.cl_fr_stages: ttk.Frame = None # type: ignore
        self.cl_stage_vars: dict[str, tk.StringVar] = {}
        self.cl_stage_ents: dict[str, ttk.Entry] = {}

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
        self.cl_var_rx = tk.StringVar(parent)
        ttk.Label(parent, text="Rx Gain (0-1):").grid(row=row,column=0, sticky=tk.W)
        self.cl_ent_rx = ttk.Entry(parent, textvariable=self.cl_var_rx, width=5)
        self.cl_ent_rx.grid(row=row,column=1, sticky=tk.E)
        row += 1
        self.cl_fr_stages = ttk.Frame(parent)
        self.cl_fr_stages.columnconfigure(1, weight=1)
        self.cl_fr_stages.grid(row=row,column=0,columnspan=2, sticky=tk.NSEW)
        return row

    def set_stages(self, stages):
        """Rebuild the gain stage entries from {name: GainStage}, as declared by the device"""
        for w in self.cl_fr_stages.winfo_children():
            w.destroy()
        self.cl_stage_vars = {}
        self.cl_stage_ents = {}
        for i, (name, st) in enumerate(stages.items()):
            var = tk.StringVar(self.cl_fr_stages)
            ttk.Label(self.cl_fr_stages, text=f"Rx {name} Gain (dB):").grid(row=i,column=0, sticky=tk.W)
            ent = ttk.Entry(self.cl_fr_stages, textvariable=var, width=5)
            ent.grid(row=i,column=1, sticky=tk.E)
            self.cl_stage_vars[name] = var
            self.cl_stage_ents[name] = ent
        return self.cl_stage_ents
