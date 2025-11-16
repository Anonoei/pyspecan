"""Controller for SWEPT mode"""
import argparse
import numpy as np

from .base import Controller
from .base import define_args as base_args
# from .arc.plot_base import define_args as freq_args
from .panels import PanelController, PanelChild, Panel
from .plot_base import FreqPlotController, BlitPlot

from .swept import plots

class ModeConfig:
    psd = True
    spg = False

def args_swept(parser: argparse.ArgumentParser):
    ctrl = base_args(parser)
    # freq_args(parser)
    # mode = parser.add_argument_group("SWEPT mode")
    # mode.add_argument("--psd", action="store_false", help="show psd")
    # mode.add_argument("--spg", action="store_true", help="show spectrogram")

class ControllerSwept(Controller):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.panel = PanelController(self, self.view.panel, plots)
        child = self.panel.rows[0]
        pane = self.panel.cols[child][0]
        pane.var_view.set("PSD")
        self.panel.set_view(None, child, pane)
        self.draw()
