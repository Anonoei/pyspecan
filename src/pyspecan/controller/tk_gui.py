"""Initialize tkGUI Controller"""
import threading
import time
import datetime as dt

import tkinter as tk

from .base import Controller as _Controller

from ..config import config, Mode

from ..utils import dialog
from ..utils.time import strfmt_td

from ..model.model import Model
from ..model.reader import Format
from ..view.tk_gui import View as GUI

# from .GUI.manager import Manager
from ..backend.mpl.plot import BlitPlot
# from ..view.tkGUI.base import GUIFreqPlot

from .tkGUI.base import FreqPlotController
from .tkGUI.swept import ControllerSwept
from .tkGUI.rt import ControllerRT

from ..backend.tk import theme as theme_tk

class Controller(_Controller):
    """tkGUI Controller"""
    def __init__(self, model: Model, view: GUI, ref_level, scale, vbw, window):
        super().__init__(model, view)
        self.view: GUI = self.view # type hints
        self.running = False
        self._stop = False
        self.time_show = 50.0
        self._last_f = None

        self.view.sld_samp.scale.config(from_=0, to=self.model.reader.max_samp) # resolution=self.model.block_size
        self.view.sld_samp.scale.config(command=self.set_samp)

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

        self.view.cb_style.config(values=[k for k in theme_tk.theme.keys()])
        self.view.cb_style.bind("<<ComboboxSelected>>", self.set_theme)

        self.thread: threading.Thread = None # type: ignore

        self.view.var_style.set("Dark")
        self.set_theme()

        if config.MODE == Mode.SWEPT:
            self.plot = ControllerSwept(self.view.plot, ref_level, scale, vbw, window)
        elif config.MODE == Mode.RT:
            self.plot = ControllerRT(self.view.plot, ref_level, scale, vbw, window)
        self.draw()

    def start(self):
        if self.running:
            return
        if self.model.reader.path is None:
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
        if isinstance(self.plot, FreqPlotController):
            vbw = self.plot.vbw
            window = self.plot.window
            if not isinstance(self.view.plot.plotter, BlitPlot):
                self.view.plot.plotter.cla()
                print("Cleared plot!")
            self._check_f()
            self.plot.plot(self.model.f, self.model.psd(vbw, window))
            # self.plot.update()

        ptime = (time.perf_counter() - ptime)
        self.view.var_draw_time.set(f"{ptime:06.3f}s")
        self.draw_tb()
        # print(f"Plotted in {ptime*1000:.1f}ms")
        return ptime

    def _check_f(self):
        def _update_f():
            return (self.model.f[0], self.model.f[-1]+(self.model.f[-1]-self.model.f[-2]), len(self.model.f))
        if self._last_f is None:
            self._last_f = _update_f()
            self.plot.update_f(self._last_f)
        elif not self.model.f[0] == self._last_f[0] and not len(self.model.f) == self._last_f[2]:
            self._last_f = _update_f()
            self.plot.update_f(self._last_f)


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
        self.view.var_samp.set(self.model.reader.cur_samp)

        self.view.var_time_cur.set(strfmt_td(dt.timedelta(seconds=self.model.cur_time())))
        self.view.var_time_tot.set(strfmt_td(dt.timedelta(seconds=self.model.tot_time())))

    def draw_ctrl(self):
        self.view.var_file.set(str(self.model.reader.path))
        self.view.var_file_fmt.set(str(self.model.reader.fmt.name))

        self.view.var_fs.set(str(self.model.Fs))
        self.view.var_cf.set(str(self.model.cf))

    def draw_view(self):
        pass

    def set_samp(self, *args, **kwargs):
        self.stop()
        samp = self.view.var_samp.get()
        self.model.reader.cur_samp = samp
        self.draw_tb()
        # print(samp)

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
        self.view.sld_samp.scale.config(from_=0, to=self.model.reader.max_samp) # resolution=self.model.block_size
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
            self.draw_tb()
        except ValueError:
            pass
        self.view.var_fs.set(str(self.model.Fs))
        self.draw_ctrl()

    def set_cf(self, *args, **kwargs):
        cf = self.view.var_cf.get()
        try:
            cf = float(cf)
            self.model.cf = cf
        except ValueError:
            pass
        self.view.var_cf.set(str(self.model.cf))
        self.draw_ctrl()

    def set_theme(self, *args, **kwargs):
        style = self.view.var_style.get()
        theme_tk.get(style)(self.view.root) # pyright: ignore[reportCallIssue]
