"""Controller for LIVE sink"""
import argparse
import datetime as dt
import tkinter as tk

import numpy as np
import pysdrlib

from ...utils import args
from .sink import Sink, args_sink

from .dispatch import CMD
# from .arc.plot_base import define_args as freq_args
from .panels import PanelController, PanelChild, Panel
from .plot_base import FreqPlotController, BlitPlot

from .swept import plots

from ...utils.time import strfmt_td

class SinkConfig:
    pass

def args_live(parser):
    sink = args.get_group(parser, "Sink (LIVE)")
    args_sink(sink)

class SinkLive(Sink):
    def __init__(self, ctrl):
        super().__init__(ctrl)

        self.ctrl.view.cb_dev.config(values=list([d for d in pysdrlib.devices.ls()]))
        self.ctrl.view.cb_dev.bind("<<ComboboxSelected>>", self.handle_event)

        self.ctrl.view.ent_rx_rf.bind("<Return>", self.handle_event)
        self.ctrl.view.ent_rx_if.bind("<Return>", self.handle_event)
        self.ctrl.view.ent_rx_bb.bind("<Return>", self.handle_event)
        self.ctrl.view.var_rx_rf.set(str(self.ctrl.model.sink.get_rx_rf()))
        self.ctrl.view.var_rx_if.set(str(self.ctrl.model.sink.get_rx_if()))
        self.ctrl.view.var_rx_bb.set(str(self.ctrl.model.sink.get_rx_bb()))
        self.toggle_gains()

    def start(self):
        if self.ctrl.model.sink.dev is None:
            print("sink is not fully initialized, failed to get device")
            return
        self.ctrl.view.btn_start.config(state=tk.DISABLED)
        self.ctrl.view.btn_stop.config(state=tk.ACTIVE)
        self.ctrl.dispatch.queue.put(CMD.START)

    def stop(self):
        self.ctrl.view.btn_stop.config(state=tk.DISABLED)
        self.ctrl.view.btn_start.config(state=tk.ACTIVE)
        self.ctrl.dispatch.queue.put(CMD.STOP)

    def reset(self):
        self.ctrl.dispatch.queue.put(CMD.RESET)
        self.stop()

    def draw_tb(self):
        pass

    def draw_ctrl(self):
        self.ctrl.view.var_dev.set(str(type(self.ctrl.model.sink.dev).__name__))
        self.ctrl.view.var_rx_rf.set(str(self.ctrl.model.sink.get_rx_rf()))
        self.ctrl.view.var_rx_if.set(str(self.ctrl.model.sink.get_rx_if()))
        self.ctrl.view.var_rx_bb.set(str(self.ctrl.model.sink.get_rx_bb()))

    def toggle_gains(self):
        if not self.ctrl.model.sink.has_rx_rf():
            self.ctrl.view.fr_rx_rf.grid_forget()
        else:
            self.ctrl.view.fr_rx_rf.grid()
        if not self.ctrl.model.sink.has_rx_if():
            self.ctrl.view.fr_rx_if.grid_forget()
        else:
            self.ctrl.view.fr_rx_if.grid()
        if not self.ctrl.model.sink.has_rx_bb():
            self.ctrl.view.fr_rx_bb.grid_forget()
        else:
            self.ctrl.view.fr_rx_bb.grid()

    # --- GUI bind events and setters --- #
    def handle_event(self, event):
        if event.widget == self.ctrl.view.cb_dev:
            self.set_device(self.ctrl.view.var_dev.get())
        elif event.widget == self.ctrl.view.ent_rx_rf:
            self.set_rx_rf(self.ctrl.view.var_rx_rf.get())
        elif event.widget == self.ctrl.view.ent_rx_if:
            self.set_rx_if(self.ctrl.view.var_rx_if.get())
        elif event.widget == self.ctrl.view.ent_rx_bb:
            self.set_rx_bb(self.ctrl.view.var_rx_bb.get())

    def set_device(self, device):
        self.ctrl.model.sink.set_device(device)
        print(f"Device set to '{self.ctrl.model.sink.name}'")
        self.draw_tb()
        self.draw_ctrl()
        self.toggle_gains()

    def set_rx_rf(self, gain):
        try:
            gain = int(gain)
            self.ctrl.model.sink.set_rx_rf(gain)
        except ValueError:
            pass
        self.draw_ctrl()

    def set_rx_if(self, gain):
        try:
            gain = int(gain)
            self.ctrl.model.sink.set_rx_if(gain)
        except ValueError:
            pass
        self.draw_ctrl()

    def set_rx_bb(self, gain):
        try:
            gain = int(gain)
            self.ctrl.model.sink.set_rx_bb(gain)
        except ValueError:
            pass
        self.draw_ctrl()
