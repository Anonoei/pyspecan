import threading
import time
import datetime as dt

import tkinter as tk
import matplotlib.pyplot as plt

from ..utils import dialog
from ..utils.time import strfmt_td

from ..model.model import Model
from ..model.model import WindowLUT
from ..model.reader import Format
from ..view.gui import GUI

from ..view.GUI.psd import PSD as viewPSD
from ..view.GUI.persistent import Persistent as viewPersistent

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

        self.view.btn_file.config(command=self.set_path)
        self.view.cb_file_fmt.config(values=list([v.name for v in Format]))
        self.view.cb_file_fmt.bind("<<ComboboxSelected>>", self.set_dtype)
        self.view.ent_fs.bind("<Return>", self.set_fs)
        self.view.ent_cf.bind("<Return>", self.set_cf)

        self.thread: threading.Thread = None # type: ignore

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
        self.view.reset()
        self.draw_tb()

    def prev(self):
        self.stop()
        return self._prev()

    def next(self):
        self.stop()
        return self._next()

    def loop(self):
        while self.running:
            ltime = time.perf_counter()
            if not self._next():
                break
            ltime = (time.perf_counter() - ltime)
            wait = (self.time_show/1000)+ltime
            # print(f"loop waiting for {wait:.4f}s")
            time.sleep(wait)

    def _plot(self):
        # PSD
        vbw = self.view.plot.vbw
        window = self.view.plot.window
        self.view.plot.plot(0, self.model.f, self.model.psd(vbw, window))
        self.view.plot.update()
        self.draw_tb()

    def _prev(self):
        reading = self.model.prev()
        if reading:
            # self.view.plot.ax(0).cla()
            self._plot()
            # self.view.plot.plot(0, self.model.f, self.model.psd)
            # self.view.plot.update()
            # self.draw_tb()
        return reading

    def _next(self):
        reading = self.model.next()
        if reading:
            # self.view.plot.ax(0).cla()
            self._plot()
            # self.view.plot.plot(0, self.model.f, self.model.psd)
            # self.view.plot.update()
            # self.draw_tb()
        return reading

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
