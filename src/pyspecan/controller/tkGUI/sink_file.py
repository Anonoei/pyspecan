"""Controller for FILE sink"""
import argparse
import datetime as dt
import tkinter as tk

import numpy as np

from ...utils import args
from .sink import Sink, args_sink

from .dispatch import CMD
# from .arc.plot_base import define_args as freq_args
from .panels import PanelController, PanelChild, Panel
from .plot_base import FreqPlotController, BlitPlot

from .swept import plots

from ...utils import dialog
from ...utils.time import strfmt_td
from ...model.sink.file import Format

class SinkConfig:
    pass

def args_file(parser: argparse.ArgumentParser):
    sink = args.get_group(parser, "Sink (FILE)")
    args_sink(sink)

class SinkFile(Sink):
    def __init__(self, ctrl):
        super().__init__(ctrl)
        self.ctrl.view.sink.tb_sld_samp.scale.config(from_=0, to=self.ctrl.model.sink.max_samp) # resolution=self.model.block_size
        self.ctrl.view.sink.tb_sld_samp.scale.config(command=self.handle_sld_samp)

        self.ctrl.view.sink.tb_btn_prev.config(command=self.prev)
        self.ctrl.view.sink.tb_btn_next.config(command=self.next)

        self.ctrl.view.sink.cl_btn_file.config(command=self.handle_btn_file)
        self.ctrl.view.sink.cl_cb_file_fmt.config(values=list([v.name for v in Format]))
        self.ctrl.view.sink.cl_cb_file_fmt.bind("<<ComboboxSelected>>", self.handle_event)

    def start(self):
        if self.ctrl.model.sink.get_path() is None:
            print("sink is not fully initialized, failed to get filepath")
            return
        self.ctrl.view.tb_btn_start.config(state=tk.DISABLED)
        self.ctrl.view.tb_btn_stop.config(state=tk.ACTIVE)
        self.ctrl.dispatch.send(CMD.START)

    def stop(self):
        self.ctrl.view.tb_btn_stop.config(state=tk.DISABLED)
        self.ctrl.view.tb_btn_start.config(state=tk.ACTIVE)
        self.ctrl.dispatch.send(CMD.STOP)

    def reset(self):
        self.ctrl.dispatch.send(CMD.RESET)
        self.stop()

    def prev(self):
        self.ctrl.dispatch.send(CMD.PREV)

    def next(self):
        self.ctrl.dispatch.send(CMD.NEXT)

    def draw_tb(self):
        self.ctrl.view.sink.tb_var_samp.set(self.ctrl.model.sink.cur_samp)

        self.ctrl.view.sink.tb_var_time_cur.set(strfmt_td(dt.timedelta(seconds=self.ctrl.model.sink.cur_time())))
        self.ctrl.view.sink.tb_var_time_tot.set(strfmt_td(dt.timedelta(seconds=self.ctrl.model.sink.tot_time())))

    def draw_cl(self):
        self.ctrl.view.sink.cl_var_file.set(str(self.ctrl.model.sink.get_path()))
        self.ctrl.view.sink.cl_var_file_fmt.set(str(self.ctrl.model.sink.get_fmt().name))


    # --- GUI bind events and setters --- #
    def handle_event(self, event):
        if event.widget == self.ctrl.view.sink.cl_cb_file_fmt:
            self.set_dtype(self.ctrl.view.sink.cl_var_file_fmt.get())
    def handle_btn_file(self):
        self.log.trace("handle_btn_file()")
        self.set_path(dialog.get_file(False))

    def handle_sld_samp(self, *args):
        self.log.trace("handle_sld_samp()")
        self.set_samp(self.ctrl.view.sink.tb_var_samp.get())

    def set_samp(self, samp):
        self.log.trace("set_samp(%s)", samp)
        self.stop()
        self.ctrl.model.sink.cur_samp = samp
        self.draw_tb()
        # print(samp)

    def set_path(self, path):
        self.log.trace("set_path(%s)", path)
        self.ctrl.model.sink.set_path(path)
        print(f"Path set to '{self.ctrl.model.sink.get_path()}'")
        self.ctrl.view.sink.tb_sld_samp.scale.config(from_=0, to=self.ctrl.model.sink.max_samp) # resolution=self.model.block_size
        self.draw_tb()
        self.draw_cl()
    def set_dtype(self, dtype):
        self.log.trace("set_dtype(%s)", dtype)
        self.ctrl.model.sink.set_fmt(dtype)
        self.draw_tb()
        self.draw_cl()
