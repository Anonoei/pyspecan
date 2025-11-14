"""Controller for RT mode"""
import argparse
import time

import numpy as np

from ...utils import matrix
from ...backend.mpl.color import cmap

from .base import Controller
from .base import define_args as base_args
# from .arc.plot_base import define_args as freq_args
from .panels import PanelController, PanelChild, Panel
from .plot_base import FreqPlotController, BlitPlot

from .rt import plots

class ModeConfig:
    x = 1001
    y = 600
    cmap = "hot"

def args_rt(parser: argparse.ArgumentParser):
    ctrl = base_args(parser)
    # freq_args(parser)
    mode = parser.add_argument_group("RT mode")
    mode.add_argument("--x", default=ModeConfig.x, type=int, help="histogram x pixels")
    mode.add_argument("--y", default=ModeConfig.y, type=int, help="histogram y pixels")
    mode.add_argument("--cmap", default=ModeConfig.cmap, choices=[k for k in cmap.keys()], help="histogram color map")

class PanelControllerRT(PanelController):
    def set_settings(self, child, pane):
        pane.cb_view.config(values=list(k for k in plots.keys()))
        pane.cb_view.bind("<<ComboboxSelected>>", lambda e,c=child, p=pane: self.set_view(e,c,p))

    def set_view(self, e, child: PanelChild, pane: Panel):
        view = pane.var_view.get()
        if view in plots:
            if self.view[child][pane] is not None:
                pane.wgts = {}
                pane.sets = {}
                for ch in pane.fr_main.winfo_children():
                    ch.destroy()
                for ch in pane.settings.winfo_children():
                    ch.destroy()
            plot = plots[view](self.parent, pane)
            self.view[child][pane] = plot

class ControllerRT(Controller):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.panel = PanelControllerRT(self, self.view.panel)
        child = self.panel.rows[0]
        pane = self.panel.cols[child][0]
        pane.var_view.set("PST")
        self.panel.set_view(None, child, pane)
        self.draw()

    def loop(self):
        while self.running:
            time_show = self.time_show/1000 # convert ms to s
            valid, ptime = self._next()
            if not valid or ptime is None:
                break
            wait = time_show-ptime
            if wait > 0:
                self.view.lbl_msg.configure(text="")
                time.sleep(wait)
            else:
                # self.model.skip_time(-wait)
                self.view.lbl_msg.configure(text="OVERFLOW")
