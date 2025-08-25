import tkinter as tk
import tkinter.ttk as ttk

from ..config import config, Mode

from .GUI.plot.base import GUIPlot, GUIBlitPlot
from .GUI.plot import s as plots

class GUI:
    def __init__(self, view, root=tk.Tk()):
        self.view = view
        self.root = root
        self.root.title(f"pyspecan | {config.MODE.value}")
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        self._main = tk.Frame(self.root)
        self._main.pack(expand=True, fill=tk.BOTH)

        self.fr_tb = tk.Frame(self._main, height=20, highlightbackground="black",highlightthickness=1)
        self.draw_tb(self.fr_tb)
        self.fr_tb.pack(side=tk.TOP, fill=tk.X, )

        self.main = tk.PanedWindow(self._main, orient=tk.HORIZONTAL)
        self.main.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.fr_ctrl = tk.Frame(self.main, width=100, highlightbackground="black",highlightthickness=1)
        self.draw_ctrl(self.fr_ctrl)
        self.main.add(self.fr_ctrl)

        self.fr_view = tk.Frame(self.main, highlightbackground="black",highlightthickness=1)
        self.plot: GUIPlot | GUIBlitPlot = None # type: ignore
        # self.draw_view(self.fr_view)
        self.main.add(self.fr_view)

    def draw_tb(self, parent):
        col = 0
        self.var_progress = tk.StringVar(parent)
        self.lbl_progress = tk.Label(parent, textvariable=self.var_progress)
        self.lbl_progress.grid(row=0, column=col, sticky=tk.NSEW)
        self.var_percent = tk.DoubleVar(parent)
        self.pb_percent = ttk.Progressbar(parent, variable=self.var_percent, length=150)
        self.pb_percent.grid(row=1,column=col, ipadx=2,ipady=2, sticky=tk.NSEW)
        col += 1
        self.var_time_cur = tk.StringVar(parent)
        self.var_time_tot = tk.StringVar(parent)
        self.lbl_time_cur = tk.Label(parent, textvariable=self.var_time_cur)
        self.lbl_time_cur.grid(row=0,column=col)
        self.lbl_time_tot = tk.Label(parent, textvariable=self.var_time_tot)
        self.lbl_time_tot.grid(row=1,column=col)
        col += 1
        ttk.Separator(parent, orient=tk.VERTICAL).grid(row=0,rowspan=2,column=col, padx=5, sticky=tk.NS)

        col += 1
        tk.Label(parent, text="Sweep").grid(row=0,column=col)
        self.var_time = tk.StringVar(parent)
        self.ent_time = tk.Entry(parent, textvariable=self.var_time, width=5)
        self.ent_time.grid(row=1,column=col, padx=2, pady=2)

        col += 1
        ttk.Separator(parent, orient=tk.VERTICAL).grid(row=0,rowspan=2,column=col, padx=5, sticky=tk.NS)
        col += 1
        self.btn_prev = tk.Button(parent, text="Prev")
        self.btn_prev.grid(row=0,rowspan=2,column=col, padx=2,pady=2)
        col += 1
        self.btn_next = tk.Button(parent, text="Next")
        self.btn_next.grid(row=0,rowspan=2,column=col, padx=2,pady=2)
        col += 1
        self.btn_start = tk.Button(parent, text="Start")
        self.btn_start.grid(row=0,rowspan=2,column=col, padx=2,pady=2, sticky=tk.NS)
        col += 1
        self.btn_stop = tk.Button(parent, text="Stop", state=tk.DISABLED)
        self.btn_stop.grid(row=0,rowspan=2,column=col, padx=2,pady=2, sticky=tk.NS)
        col += 1
        self.btn_reset = tk.Button(parent, text="Reset")
        self.btn_reset.grid(row=0,rowspan=2,column=col, padx=2,pady=2, sticky=tk.NS)
        col += 1
        ttk.Separator(parent, orient=tk.VERTICAL).grid(row=0,rowspan=2,column=col, padx=5, sticky=tk.NS)

        col += 1
        self.var_draw_time = tk.StringVar(parent)
        self.lbl_draw_time = tk.Label(parent, textvariable=self.var_draw_time)
        tk.Label(parent, text="Draw").grid(row=0,column=col, sticky=tk.E)
        self.lbl_draw_time.grid(row=1,column=col, sticky=tk.E)
        parent.grid_columnconfigure(col, weight=1)


    def draw_ctrl(self, parent):
        root = tk.Frame(parent) # File reader
        root.columnconfigure(2, weight=1)
        row = 0
        self.var_file = tk.StringVar(root)
        self.btn_file = tk.Button(root, text="File")
        self.btn_file.grid(row=row,column=0, sticky=tk.W)
        self.ent_file = tk.Entry(root, textvariable=self.var_file, state=tk.DISABLED, width=10)
        self.ent_file.grid(row=row,column=1,columnspan=2, sticky=tk.NSEW)
        row += 1
        tk.Label(root, text="Format:").grid(row=row,column=0,sticky=tk.W)
        self.var_file_fmt = tk.StringVar(root)
        self.cb_file_fmt = ttk.Combobox(root, textvariable=self.var_file_fmt, width=5)
        self.cb_file_fmt.grid(row=row,column=1, sticky=tk.W)
        root.pack(padx=2,pady=2, fill=tk.X)

        root = tk.Frame(parent) # File params
        row = 0
        self.var_fs = tk.StringVar(root)
        tk.Label(root, text="Sample rate:").grid(row=row,column=0, sticky=tk.W)
        self.ent_fs = tk.Entry(root, textvariable=self.var_fs, width=10)
        self.ent_fs.grid(row=row,column=1, sticky=tk.W)
        row += 1
        self.var_cf = tk.StringVar(root)
        tk.Label(root, text="Center freq:").grid(row=row,column=0, sticky=tk.W)
        self.ent_cf = tk.Entry(root, textvariable=self.var_cf, width=10)
        self.ent_cf.grid(row=row,column=1, sticky=tk.W)
        root.pack(padx=2,pady=2, fill=tk.X)

    # def draw_view(self, parent):
    #     if config.MODE == Mode.SWEPT:
    #         self.plot = plots["PSD"](self, parent)
    #     elif config.MODE == Mode.RT:
    #         self.plot = plots["Persistent"](self, parent)

    def mainloop(self):
        self.root.mainloop()

    def quit(self):
        self.root.quit()
        self.root.destroy()
