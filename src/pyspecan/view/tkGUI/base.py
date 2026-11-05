"""Create a GUI view"""
import tkinter as tk
import tkinter.ttk as ttk

from ..base import View as _View

from ...backend.tk import widgets
from ...backend.mpl import theme as theme_mpl

from .sink import Sink
from .panels import PanelView

LUT = {
    "fr": ttk.Frame,
    "ent": ttk.Entry,
    "btn": ttk.Button,
    "lbl": ttk.Label,
    "cb": ttk.Combobox,
    "sld": widgets.Scale,

    "var": tk.Variable,
    "vs": tk.StringVar,
    "vi": tk.IntVar,
}

def args_view(parser):
    pass

class View(_View):
    """Parent tkGUI view class"""

    def __init__(self, sink, root=None, **kwargs):
        self.root = root or tk.Tk()
        self.root.title("pyspecan")

        theme_mpl.get(kwargs.get("theme", "Dark"))() # Set matplotlib theme

        self._main = ttk.Frame(self.root)
        self._main.pack(expand=True, fill=tk.BOTH)

        self.fr_tb = ttk.Frame(self._main, height=20)

        self.main = ttk.PanedWindow(self._main, orient=tk.HORIZONTAL)

        self.fr_view = ttk.Frame(self.main)
        self.panel = PanelView(self.fr_view)

        self.fr_cl = ttk.Frame(self.main, width=100)

        # toolbar
        self.tb_fr_sink = ttk.Frame(self.fr_tb)
        self.tb_fr_time = ttk.Frame(self.fr_tb)
        self.tb_var_sweep: tk.StringVar = None # type: ignore
        self.tb_ent_sweep: ttk.Entry = None # type: ignore
        self.tb_var_show: tk.StringVar = None # type: ignore
        self.tb_ent_show: ttk.Entry = None # type: ignore
        self.tb_fr_btn = ttk.Frame(self.fr_tb)
        self.tb_btn_start: ttk.Button = None # type: ignore
        self.tb_btn_stop: ttk.Button = None # type: ignore
        self.tb_btn_reset: ttk.Button = None # type: ignore
        self.tb_fr_msg = ttk.Frame(self.fr_tb)
        self.tb_lbl_msg: ttk.Label = None # type: ignore
        self.tb_var_draw_time: tk.StringVar = None # type: ignore
        self.tb_lbl_draw_time: ttk.Label = None # type: ignore
        # control panel
        self.cl_fr_sink = ttk.Frame(self.fr_cl)
        self.cl_fr_view = ttk.Frame(self.fr_cl)
        self.cl_var_fs: tk.StringVar = None # type: ignore
        self.cl_ent_fs: ttk.Entry = None # type: ignore
        self.cl_var_cf: tk.StringVar = None # type: ignore
        self.cl_ent_cf: ttk.Entry = None # type: ignore
        self.cl_var_nfft_exp: tk.StringVar = None # type: ignore
        self.cl_ent_nfft_exp: ttk.Entry = None # type: ignore
        self.cl_lbl_nfft: ttk.Label = None # type: ignore
        self.cl_var_overlap: tk.StringVar = None # type: ignore
        self.cl_ent_overlap: ttk.Entry = None # type: ignore
        self.cl_fr_lbls = ttk.Frame(self.fr_cl)
        self.cl_lbl_block_size: ttk.Label = None # type: ignore
        self.cl_lbl_sweep_samples: ttk.Label = None # type: ignore

        self.sink: Sink = sink(self)

        self.draw_tb()
        self.sink.finish_tb()
        self.fr_tb.pack(side=tk.TOP, fill=tk.X)

        ttk.Separator(self._main, orient=tk.HORIZONTAL).pack(fill=tk.X)

        self.main.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.draw_cl()
        self.sink.finish_cl()
        self.sink.finish_cl()
        self.main.add(self.fr_cl)

        self.main.add(self.fr_view)

    def draw_tb(self):
        """Draw toolbar frame"""
        self.sink.draw_tb(self.tb_fr_sink)
        self.tb_fr_sink.pack(fill=tk.Y, side=tk.LEFT)

        ttk.Separator(self.fr_tb, orient=tk.VERTICAL).pack(fill=tk.Y, side=tk.LEFT)

        self.draw_tb_time(self.tb_fr_time)
        self.tb_fr_time.pack(fill=tk.Y, side=tk.LEFT)

        ttk.Separator(self.fr_tb, orient=tk.VERTICAL).pack(fill=tk.Y, side=tk.LEFT)

        self.draw_tb_btn(self.tb_fr_btn)
        self.tb_fr_btn.pack(fill=tk.Y, side=tk.LEFT, pady=2)

        ttk.Separator(self.fr_tb, orient=tk.VERTICAL).pack(fill=tk.Y, side=tk.LEFT)

        self.draw_tb_msg(self.tb_fr_msg)
        self.tb_fr_msg.pack(fill=tk.BOTH, side=tk.RIGHT)

    def draw_tb_time(self, parent, col=0):
        ttk.Label(parent, text="Sweep").grid(row=0,column=col)
        self.tb_var_sweep = tk.StringVar(parent)
        self.tb_ent_sweep = ttk.Entry(parent, textvariable=self.tb_var_sweep, width=8)
        self.tb_ent_sweep.grid(row=1,column=col, padx=2, pady=2)
        col += 1
        ttk.Label(parent, text="Show").grid(row=0,column=col)
        self.tb_var_show = tk.StringVar(parent)
        self.tb_ent_show = ttk.Entry(parent, textvariable=self.tb_var_show, width=8)
        self.tb_ent_show.grid(row=1,column=col, padx=2, pady=2)
        col += 1
        return col

    def draw_tb_btn(self, parent, col=0):
        parent.grid_rowconfigure(0, weight=1)
        self.tb_btn_start = ttk.Button(parent, text="Start")
        self.tb_btn_start.grid(row=0,rowspan=2,column=col, padx=2, sticky=tk.NS)
        col += 1
        self.tb_btn_stop = ttk.Button(parent, text="Stop", state=tk.DISABLED)
        self.tb_btn_stop.grid(row=0,rowspan=2,column=col, padx=2, sticky=tk.NS)
        col += 1
        self.tb_btn_reset = ttk.Button(parent, text="Reset")
        self.tb_btn_reset.grid(row=0,rowspan=2,column=col, padx=2, sticky=tk.NS)
        col += 1
        return col

    def draw_tb_msg(self, parent, col=0):
        self.tb_lbl_msg = ttk.Label(parent, text="")
        self.tb_lbl_msg.grid(row=0,column=col, rowspan=2, sticky=tk.E)
        parent.grid_columnconfigure(col, weight=1)
        col += 1
        self.tb_var_draw_time = tk.StringVar(parent)
        self.tb_lbl_draw_time = ttk.Label(parent, textvariable=self.tb_var_draw_time)
        ttk.Label(parent, text="Draw").grid(row=0,column=col, sticky=tk.E)
        self.tb_lbl_draw_time.grid(row=1,column=col, sticky=tk.E)
        parent.grid_columnconfigure(col, weight=1)
        return col

    def draw_cl(self):
        """Draw control frame"""
        self.sink.draw_cl(self.cl_fr_sink)
        self.cl_fr_sink.pack(padx=2,pady=2, fill=tk.X)

        ttk.Separator(self.fr_cl, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)

        self.draw_cl_view(self.cl_fr_view)
        self.cl_fr_view.pack(padx=2,pady=2, fill=tk.X)

        ttk.Separator(self.fr_cl, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)

        self.draw_cl_lbls(self.cl_fr_lbls)
        self.cl_fr_lbls.pack(padx=2,pady=2, fill=tk.X)

    def draw_cl_view(self, parent, row=0):
        parent.columnconfigure(2, weight=1)
        self.cl_var_fs = tk.StringVar(parent)
        ttk.Label(parent, text="Sample rate:").grid(row=row,column=0, sticky=tk.W)
        self.cl_ent_fs = ttk.Entry(parent, textvariable=self.cl_var_fs, width=10)
        self.cl_ent_fs.grid(row=row,column=1, columnspan=2,sticky=tk.E)
        row += 1
        self.cl_var_cf = tk.StringVar(parent)
        ttk.Label(parent, text="Center freq:").grid(row=row,column=0, sticky=tk.W)
        self.cl_ent_cf = ttk.Entry(parent, textvariable=self.cl_var_cf, width=10)
        self.cl_ent_cf.grid(row=row,column=1, columnspan=2,sticky=tk.E)
        row += 1
        self.cl_var_nfft_exp = tk.StringVar(parent)
        ttk.Label(parent, text="NFFT 2^").grid(row=row,column=0, sticky=tk.W)
        self.cl_ent_nfft_exp = ttk.Entry(parent, textvariable=self.cl_var_nfft_exp, width=2)
        self.cl_ent_nfft_exp.grid(row=row,column=1, sticky=tk.W)
        self.cl_lbl_nfft = ttk.Label(parent)
        self.cl_lbl_nfft.grid(row=row,column=2, sticky=tk.E)
        row += 1
        self.cl_var_overlap = tk.StringVar(parent)
        ttk.Label(parent, text="RT overlap:").grid(row=row,column=0, sticky=tk.W)
        self.cl_ent_overlap = ttk.Entry(parent, textvariable=self.cl_var_overlap, width=4)
        self.cl_ent_overlap.grid(row=row,column=1, sticky=tk.W)
        return row

    def draw_cl_lbls(self, parent, row=0):
        ttk.Label(parent, text="Block size: ").grid(row=row, column=0, sticky=tk.W)
        self.cl_lbl_block_size = ttk.Label(parent)
        self.cl_lbl_block_size.grid(row=row, column=1)
        row += 1
        ttk.Label(parent, text="Sweep size: ").grid(row=row, column=0, sticky=tk.W)
        self.cl_lbl_sweep_samples = ttk.Label(parent)
        self.cl_lbl_sweep_samples.grid(row=row, column=1)
        return row

    def mainloop(self):
        self.root.mainloop()
