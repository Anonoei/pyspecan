"""tkGUI SWEPT mode"""
import argparse

from ...utils import args
from .mode import Mode, args_mode

from .panels import PanelController, PanelChild, Panel
from .plot_base import FreqPlotController, BlitPlot

from .swept import plots

class ModeConfig:
    psd = True
    spg = False

def args_swept(parser: argparse.ArgumentParser):
    mode = args.get_group(parser, "Mode (SWEPT)")
    args_mode(mode)
    # freq_args(parser)
    # mode = parser.add_argument_group("SWEPT mode")
    # mode.add_argument("--psd", action="store_false", help="show psd")
    # mode.add_argument("--spg", action="store_true", help="show spectrogram")

class ModeSwept(Mode):
    def __init__(self, ctrl, **kwargs):
        super().__init__(ctrl)
        self.panel = PanelController(self.ctrl, self.ctrl.view.panel, plots)
        child = self.panel.rows[0]
        pane = self.panel.cols[child][0]
        pane.var_view.set("PSD")
        self.panel.set_view(None, child, pane)
