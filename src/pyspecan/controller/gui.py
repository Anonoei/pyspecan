import threading
import time
import datetime as dt

import tkinter as tk
import matplotlib.pyplot as plt

from ..config import config, Mode

from ..utils import dialog
from ..utils.time import strfmt_td

from ..model.model import Model
from ..model.reader import Format
from ..view.gui import GUI

from .GUI.plot import s as ctrlPlots
from ..view.GUI.plot import s as viewPlots

from ..view.GUI.plot.base import GUIPlot, GUIBlitPlot

class Controller:
    def __init__(self, model: Model, view: GUI):
        self.model = model
        self.view = view
        self.running = False
        self._stop = False
        self.time_show = 50.0

        self.view.ent_time.bind("<Return>", self.set_time)
        self.view.var_time.set(str(self.time_show))
        self.view.btn_prev.config(command=self.prev)
        self.view.btn_next.config(command=self.next)
        self.view.btn_start.config(command=self.start)
        self.view.btn_stop.config(command=self.stop)
        self.view.btn_reset.config(command=self.reset)
        self.view.var_draw_time.set(f"{0.0:06.3f}s")

        self.view.btn_file.config(command=self.set_path)
        self.view.cb_file_fmt.config(values=list([v.name for v in Format]))
        self.view.cb_file_fmt.bind("<<ComboboxSelected>>", self.set_dtype)
        self.view.ent_fs.bind("<Return>", self.set_fs)
        self.view.ent_cf.bind("<Return>", self.set_cf)

        self.thread: threading.Thread = None # type: ignore

        if config.MODE == Mode.SWEPT:
            self.view.plot = viewPlots["PSD"](self.view, self.view.fr_view)
            self.plot = ctrlPlots["PSD"](self.view.plot)
        elif config.MODE == Mode.RT:
            self.view.plot = viewPlots["Persistent"](self.view, self.view.fr_view)
            self.plot = ctrlPlots["Persistent"](self.view.plot)
        self.draw()

    def start(self):
        if self.running:
            return
        self.running = True
        self.view.btn_start.config(state=tk.DISABLED)
        self.view.btn_stop.config(state=tk.ACTIVE)
        self.thread = threading.Thread(target=self.loop)
        self.thread.start()

    def stop(self):
        if not self._stop and not self.running:
            return
        self.running = False
        self.view.btn_stop.config(state=tk.DISABLED)
        self.view.btn_start.config(state=tk.ACTIVE)
        self.thread.join(timeout=0.2)

    def reset(self):
        self.stop()
        self.model.reset()
        self.plot.reset()
        self.draw_tb()

    def prev(self):
        self.stop()
        return self._prev()

    def next(self):
        self.stop()
        return self._next()

    def loop(self):
        time_show = self.time_show/1000 # convert ms to s
        while self.running:
            valid, ptime = self._next()
            if not valid or ptime is None:
                break
            wait = time_show-ptime
            if wait > 0:
                # print(f"Loop waiting for {wait*1000:.1f}ms")
                time.sleep(wait)

    def _plot(self):
        ptime = time.perf_counter()
        vbw = self.plot.vbw
        window = self.plot.window
        if not isinstance(self.view.plot, GUIBlitPlot):
            self.view.plot.plotter.ax(0).cla()
            print(f"Cleared plot!")

        self.plot.plot(0, self.model.f, self.model.psd(vbw, window))
        self.plot.update()

        ptime = (time.perf_counter() - ptime)
        self.view.var_draw_time.set(f"{ptime:06.3f}s")
        self.draw_tb()
        # print(f"Plotted in {ptime*1000:.1f}ms")
        return ptime

    def _prev(self):
        valid = self.model.prev()
        tplot = None
        if valid:
            tplot = self._plot()
        return (valid, tplot)

    def _next(self):
        valid = self.model.next()
        tplot = None
        if valid:
            tplot = self._plot()
        return (valid, tplot)

    def draw(self):
        self.draw_tb()
        self.draw_ctrl()
        self.draw_view()

    def draw_tb(self):
        self.view.var_progress.set(f"{self.model.reader.cur_samp}/{self.model.reader.max_samp}")
        self.view.var_percent.set(float(self.model.reader.percent()))

        # cur_time = f"{cur_time:07.3f}" if cur_time < 1000 else f"{cur_time:.2e}"
        # tot_time = f"{tot_time:07.3f}" if tot_time < 1000 else f"{tot_time:.2e}"
        self.view.var_time_cur.set(strfmt_td(dt.timedelta(seconds=self.model.cur_time())))
        self.view.var_time_tot.set(strfmt_td(dt.timedelta(seconds=self.model.tot_time())))

    def draw_ctrl(self):
        self.view.var_file.set(str(self.model.reader.path))
        self.view.var_file_fmt.set(str(self.model.reader.fmt.name))

        self.view.var_fs.set(str(self.model.Fs))
        self.view.var_cf.set(str(self.model.cf))

    def draw_view(self):
        pass

    def set_time(self, *args, **kwargs):
        ts = self.view.var_time.get()
        try:
            ts = float(ts)
            self.time_show = ts
        except ValueError:
            pass
        self.view.var_time.set(str(self.time_show))

    def set_path(self, *args, **kwargs):
        path = dialog.get_file(False)
        if path is None:
            path = self.model.reader.path
        fmt = self.view.var_file_fmt.get()
        self.model.set_path(path, fmt)
        self.draw_tb()
        self.draw_ctrl()

    def set_dtype(self, *args, **kwargs):
        dtype = self.view.var_file_fmt.get()
        path = self.view.var_file.get()
        self.model.set_path(path, dtype)
        self.draw_tb()
        self.draw_ctrl()

    def set_fs(self, *args, **kwargs):
        fs = self.view.var_fs.get()
        try:
            fs = float(fs)
            self.model.Fs = fs
        except ValueError:
            pass
        self.view.var_fs.set(str(self.model.Fs))

    def set_cf(self, *args, **kwargs):
        cf = self.view.var_cf.get()
        try:
            cf = float(cf)
            self.model.cf = cf
        except ValueError:
            pass
        self.view.var_cf.set(str(self.model.cf))
