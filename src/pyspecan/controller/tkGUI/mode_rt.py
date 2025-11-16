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

class ControllerRT(Controller):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.panel = PanelController(self, self.view.panel, plots)
        child = self.panel.rows[0]
        pane = self.panel.cols[child][0]
        pane.var_view.set("Persistent Histogram")
        self.panel.set_view(None, child, pane)
        self.draw()
