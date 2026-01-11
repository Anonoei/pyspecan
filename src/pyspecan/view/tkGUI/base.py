"""Create a GUI view"""
import tkinter as tk
import tkinter.ttk as ttk

from ..base import View as _View
from ...config import config, Mode

from ...backend.tk import widgets
from ...backend.mpl import theme as theme_mpl

from .panels import PanelView

class View(_View):
    """Parent tkGUI view class"""

    __slots__ = (
        "root", "_main",
        "main", "fr_tb", "fr_view", "fr_ctrl", "frame",
        # toolbar
        "btn_start", "btn_stop", "btn_reset",
        "var_sweep", "ent_sweep",
        "var_show", "ent_show",
        "lbl_msg"
        "var_draw_time", "lbl_draw_time",
        # control panel
        "var_fs", "ent_fs",
        "var_cf", "ent_cf",
        "var_nfft_exp", "ent_nfft_exp",
        "lbl_nfft",
        "lbl_block_size", "lbl_sweep_samples",
    )
    def __init__(self, root=tk.Tk(), **kwargs):
        self.root = root
        self.root.title("pyspecan")

        if config.MODE == Mode.SWEPT:
            self.root.title("pyspecan | Swept")
        elif config.MODE == Mode.RT:
            self.root.title("pyspecan | Real-Time")

        theme_mpl.get(kwargs.get("theme", "Dark"))() # Set matplotlib theme

        # self.style = ttk.Style(root)

        self._main = ttk.Frame(self.root)
        self._main.pack(expand=True, fill=tk.BOTH)

        self.fr_tb = ttk.Frame(self._main, height=20)
        self.btn_start: ttk.Button = None # type: ignore
        self.btn_stop: ttk.Button = None # type: ignore
        self.btn_reset: ttk.Button = None # type: ignore
        self.var_sweep: tk.StringVar = None # type: ignore
        self.ent_sweep: ttk.Entry = None # type: ignore
        self.var_show: tk.StringVar = None # type: ignore
        self.ent_show: ttk.Entry = None # type: ignore
        self.lbl_msg: ttk.Label = None # type: ignore
        self.var_draw_time: tk.StringVar = None # type: ignore
        self.lbl_draw_time: ttk.Label = None # type: ignore
        self.draw_tb(self.fr_tb)
        self.fr_tb.pack(side=tk.TOP, fill=tk.X)

        self.main = ttk.PanedWindow(self._main, orient=tk.HORIZONTAL)
        self.main.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.fr_view = ttk.Frame(self.main)
        self.panel = PanelView(self.fr_view)

        self.fr_ctrl = ttk.Frame(self.main, width=100)
        self.var_fs: tk.StringVar = None # type: ignore
        self.ent_fs: ttk.Entry = None # type: ignore
        self.var_cf: tk.StringVar = None # type: ignore
        self.ent_cf: ttk.Entry = None # type: ignore
        self.var_nfft_exp: tk.StringVar = None # type: ignore
        self.ent_nfft_exp: ttk.Entry = None # type: ignore
        self.lbl_nfft: ttk.Label = None # type: ignore
        self.lbl_block_size: ttk.Label = None # type: ignore
        self.lbl_sweep_samples: ttk.Label = None # type: ignore
        self.draw_ctrl(self.fr_ctrl)
        self.main.add(self.fr_ctrl)

        self.main.add(self.fr_view)

    def draw_tb(self, parent, col=0):
        """Draw toolbar frame"""
        col = self.draw_tb_progress(parent, col)
        col = self.draw_tb_time(parent, col)
        col = self.draw_tb_btn(parent, col)
        col = self.draw_tb_msg(parent, col)

    def draw_tb_time(self, parent, col=0):
        ttk.Label(parent, text="Sweep").grid(row=0,column=col)
        self.var_sweep = tk.StringVar(parent)
        self.ent_sweep = ttk.Entry(parent, textvariable=self.var_sweep, width=8)
        self.ent_sweep.grid(row=1,column=col, padx=2, pady=2)
        col += 1
        ttk.Label(parent, text="Show").grid(row=0,column=col)
        self.var_show = tk.StringVar(parent)
        self.ent_show = ttk.Entry(parent, textvariable=self.var_show, width=8)
        self.ent_show.grid(row=1,column=col, padx=2, pady=2)
        col += 1
        ttk.Separator(parent, orient=tk.VERTICAL).grid(row=0,rowspan=2,column=col, padx=5, sticky=tk.NS)
        col += 1
        return col

    def draw_tb_btn(self, parent, col=0):
        self.btn_start = ttk.Button(parent, text="Start")
        self.btn_start.grid(row=0,rowspan=2,column=col, padx=2,pady=2, sticky=tk.NS)
        col += 1
        self.btn_stop = ttk.Button(parent, text="Stop", state=tk.DISABLED)
        self.btn_stop.grid(row=0,rowspan=2,column=col, padx=2,pady=2, sticky=tk.NS)
        col += 1
        self.btn_reset = ttk.Button(parent, text="Reset")
        self.btn_reset.grid(row=0,rowspan=2,column=col, padx=2,pady=2, sticky=tk.NS)
        col += 1
        ttk.Separator(parent, orient=tk.VERTICAL).grid(row=0,rowspan=2,column=col, padx=5, sticky=tk.NS)
        col += 1
        return col

    def draw_tb_msg(self, parent, col=0):
        self.lbl_msg = ttk.Label(parent, text="")
        self.lbl_msg.grid(row=0,column=col, rowspan=2, sticky=tk.E)
        parent.grid_columnconfigure(col, weight=1)
        col += 1
        self.var_draw_time = tk.StringVar(parent)
        self.lbl_draw_time = ttk.Label(parent, textvariable=self.var_draw_time)
        ttk.Label(parent, text="Draw").grid(row=0,column=col, sticky=tk.E)
        self.lbl_draw_time.grid(row=1,column=col, sticky=tk.E)
        parent.grid_columnconfigure(col, weight=1)
        return col

    def draw_ctrl(self, parent):
        """Draw control frame"""
        self.draw_ctrl_sink(parent)
        self.draw_ctrl_view(parent)
        self.draw_ctrl_lbls(parent)

    def draw_ctrl_view(self, parent):
        root = ttk.Frame(parent) # View settings
        root.columnconfigure(2, weight=1)
        row = 0
        self.var_fs = tk.StringVar(root)
        ttk.Label(root, text="Sample rate:").grid(row=row,column=0, sticky=tk.W)
        self.ent_fs = ttk.Entry(root, textvariable=self.var_fs, width=10)
        self.ent_fs.grid(row=row,column=1, columnspan=2,sticky=tk.E)
        row += 1
        self.var_cf = tk.StringVar(root)
        ttk.Label(root, text="Center freq:").grid(row=row,column=0, sticky=tk.W)
        self.ent_cf = ttk.Entry(root, textvariable=self.var_cf, width=10)
        self.ent_cf.grid(row=row,column=1, columnspan=2,sticky=tk.E)
        row += 1
        self.var_nfft_exp = tk.StringVar(root)
        ttk.Label(root, text="NFFT 2^").grid(row=row,column=0, sticky=tk.W)
        self.ent_nfft_exp = ttk.Entry(root, textvariable=self.var_nfft_exp, width=2)
        self.ent_nfft_exp.grid(row=row,column=1, sticky=tk.W)
        self.lbl_nfft = ttk.Label(root)
        self.lbl_nfft.grid(row=row,column=2, sticky=tk.E)
        root.pack(padx=2,pady=2, fill=tk.X)

    def draw_ctrl_lbls(self, parent):
        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)

        root = ttk.Frame(parent) # Useful variables
        row = 0
        ttk.Label(root, text="Block size: ").grid(row=row, column=0, sticky=tk.W)
        self.lbl_block_size = ttk.Label(root)
        self.lbl_block_size.grid(row=row, column=1)
        row += 1
        ttk.Label(root, text="Sweep size: ").grid(row=row, column=0, sticky=tk.W)
        self.lbl_sweep_samples = ttk.Label(root)
        self.lbl_sweep_samples.grid(row=row, column=1)
        root.pack(padx=2,pady=2, fill=tk.X)

    def mainloop(self):
        self.root.mainloop()

    # --- Defined in child classes --- #
    def draw_tb_progress(self, parent, col=0):
        raise NotImplementedError()
    def draw_ctrl_sink(self, parent):
        raise NotImplementedError()
