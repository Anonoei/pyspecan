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
        self.draw_tb(self.fr_tb)
        self.fr_tb.pack(side=tk.TOP, fill=tk.X)

        self.main = ttk.PanedWindow(self._main, orient=tk.HORIZONTAL)
        self.main.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.fr_view = ttk.Frame(self.main)
        self.panel = PanelView(self.fr_view)

        self.fr_ctrl = ttk.Frame(self.main, width=100)
        self.draw_ctrl(self.fr_ctrl)
        self.main.add(self.fr_ctrl)

        self.main.add(self.fr_view)

    def draw_tb(self, parent):
        """Draw toolbar frame"""
        col = 0
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
        self.btn_prev = ttk.Button(parent, text="Prev")
        self.btn_prev.grid(row=0,rowspan=2,column=col, padx=2,pady=2)
        col += 1
        self.btn_next = ttk.Button(parent, text="Next")
        self.btn_next.grid(row=0,rowspan=2,column=col, padx=2,pady=2)
        col += 1
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
        self.lbl_msg = ttk.Label(parent, text="")
        self.lbl_msg.grid(row=0,column=col, rowspan=2, sticky=tk.E)
        parent.grid_columnconfigure(col, weight=1)
        col += 1
        self.var_draw_time = tk.StringVar(parent)
        self.lbl_draw_time = ttk.Label(parent, textvariable=self.var_draw_time)
        ttk.Label(parent, text="Draw").grid(row=0,column=col, sticky=tk.E)
        self.lbl_draw_time.grid(row=1,column=col, sticky=tk.E)
        parent.grid_columnconfigure(col, weight=1)

    def draw_ctrl(self, parent):
        """Draw control frame"""
        # Model
        root = ttk.Frame(parent) # File reader
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

        root = ttk.Frame(parent) # File params
        row = 0
        self.var_fs = tk.StringVar(root)
        ttk.Label(root, text="Sample rate:").grid(row=row,column=0, sticky=tk.W)
        self.ent_fs = ttk.Entry(root, textvariable=self.var_fs, width=10)
        self.ent_fs.grid(row=row,column=1, sticky=tk.W)
        row += 1
        self.var_cf = tk.StringVar(root)
        ttk.Label(root, text="Center freq:").grid(row=row,column=0, sticky=tk.W)
        self.ent_cf = ttk.Entry(root, textvariable=self.var_cf, width=10)
        self.ent_cf.grid(row=row,column=1, sticky=tk.W)
        root.pack(padx=2,pady=2, fill=tk.X)

        root = ttk.Frame(parent) # Other params
        root.columnconfigure(2, weight=1)
        row = 0
        self.var_nfft_exp = tk.StringVar(root)
        ttk.Label(root, text="NFFT 2^").grid(row=row,column=0, sticky=tk.W)
        self.ent_nfft_exp = ttk.Entry(root, textvariable=self.var_nfft_exp, width=2)
        self.ent_nfft_exp.grid(row=row,column=1, sticky=tk.W)
        self.lbl_nfft = ttk.Label(root)
        self.lbl_nfft.grid(row=row,column=3, sticky=tk.NSEW)
        root.pack(padx=2,pady=2, fill=tk.X)

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
