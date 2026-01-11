import tkinter as tk
import tkinter.ttk as ttk

from ...config import config, Mode

from ...backend.tk import widgets
from ...backend.mpl import theme as theme_mpl

from .panels import PanelView

from .base import View as _View

class ViewLive(_View):
    __slots__ = (
        # control panel
        "var_dev", "cb_dev",
        "fr_rx_rf", "var_rx_rf", "ent_rx_rf",
        "fr_rx_if", "var_rx_if", "ent_rx_if",
        "fr_rx_bb", "var_rx_bb", "ent_rx_bb"
    )

    def __init__(self, *args, **kwargs):
        self.var_dev: tk.StringVar = None # type: ignore
        self.cb_dev: ttk.Combobox = None # type: ignore
        self.fr_rx_rf: ttk.Frame = None # type: ignore
        self.var_rx_rf: tk.StringVar = None # type: ignore
        self.ent_rx_rf: ttk.Entry = None # type: ignore
        self.fr_rx_if: ttk.Frame = None # type: ignore
        self.var_rx_if: tk.StringVar = None # type: ignore
        self.ent_rx_if: ttk.Entry = None # type: ignore
        self.fr_rx_bb: ttk.Frame = None # type: ignore
        self.var_rx_bb: tk.StringVar = None # type: ignore
        self.ent_rx_bb: ttk.Entry = None # type: ignore
        super().__init__(*args, **kwargs)
    def draw_tb_progress(self, parent, col=0):
        return col

    def draw_ctrl_sink(self, parent):
        root = ttk.Frame(parent) # Sink.LIVE
        root.columnconfigure(1, weight=1)
        row = 0
        self.var_dev = tk.StringVar(root) # TODO: switch from ent to combo
        ttk.Label(root, text="Device:").grid(row=row,column=0, sticky=tk.W)
        self.cb_dev = ttk.Combobox(root, textvariable=self.var_dev, width=20)
        # self.ent_dev = ttk.Entry(root, textvariable=self.var_dev, state=tk.DISABLED, width=10)
        self.cb_dev.grid(row=row,column=1, sticky=tk.NSEW)
        row += 1
        ttk.Separator(root, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=2, pady=5, sticky=tk.EW)
        row += 1
        self.fr_rx_rf = ttk.Frame(root)
        self.fr_rx_rf.columnconfigure(1, weight=1)
        self.var_rx_rf = tk.StringVar(self.fr_rx_rf)
        ttk.Label(self.fr_rx_rf, text="Rx RF Gain:").grid(row=0,column=0, sticky=tk.W)
        self.ent_rx_rf = ttk.Entry(self.fr_rx_rf, textvariable=self.var_rx_rf, width=3)
        self.ent_rx_rf.grid(row=0,column=1, sticky=tk.E)
        self.fr_rx_rf.grid(row=row,column=0,columnspan=2, sticky=tk.NSEW)
        # root.columnconfigure(row, weight=1)
        row += 1
        self.fr_rx_if = ttk.Frame(root)
        self.fr_rx_if.columnconfigure(1, weight=1)
        self.var_rx_if = tk.StringVar(self.fr_rx_if)
        ttk.Label(self.fr_rx_if, text="Rx IF Gain:").grid(row=0,column=0, sticky=tk.W)
        self.ent_rx_if = ttk.Entry(self.fr_rx_if, textvariable=self.var_rx_if, width=3)
        self.ent_rx_if.grid(row=0,column=1, sticky=tk.E)
        self.fr_rx_if.grid(row=row,column=0,columnspan=2, sticky=tk.NSEW)
        # root.columnconfigure(row, weight=1)
        row += 1
        self.fr_rx_bb = ttk.Frame(root)
        self.fr_rx_bb.columnconfigure(1, weight=1)
        self.var_rx_bb = tk.StringVar(self.fr_rx_bb)
        ttk.Label(self.fr_rx_bb, text="Rx BB Gain:").grid(row=0,column=0, sticky=tk.W)
        self.ent_rx_bb = ttk.Entry(self.fr_rx_bb, textvariable=self.var_rx_bb, width=3)
        self.ent_rx_bb.grid(row=0,column=1, sticky=tk.E)
        self.fr_rx_bb.grid(row=row,column=0,columnspan=2, sticky=tk.NSEW)
        # root.columnconfigure(row, weight=1)
        root.pack(padx=2,pady=2, fill=tk.X)
