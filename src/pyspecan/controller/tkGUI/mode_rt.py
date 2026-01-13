"""tkGUI RT mode"""
import argparse

from ...utils import args
from .mode import Mode, args_mode
from .plot_base import args_plot

from .panels import PanelController, PanelChild, Panel
from .plot_base import FreqPlotController, BlitPlot

from .rt import plots
from ...backend.mpl.color import cmap

class ModeConfig:
    ref_level = 0
    scale_div = 10.0
    vbw = 0.0
    window = "blackman"
    x = 1001
    y = 600
    cmap = "hot"

def args_rt(parser: argparse.ArgumentParser):
    mode = args.get_group(parser, "Mode (RT)")
    args_mode(mode)
    mode.add_argument("--x", default=ModeConfig.x, type=int, help="histogram x pixels")
    mode.add_argument("--y", default=ModeConfig.y, type=int, help="histogram y pixels")
    mode.add_argument("--cmap", default=ModeConfig.cmap, choices=[k for k in cmap.keys()], help="histogram color map")

class ModeRT(Mode):
    def __init__(self, ctrl, **kwargs):
        super().__init__(ctrl)

        self.ctrl.view.mode.cl_var_overlap.set(f"{self.ctrl.model.mode.get_overlap():.2f}")
        self.ctrl.view.mode.cl_ent_overlap.bind("<Return>", self.handle_event)
        self.panel = PanelController(self.ctrl, self.ctrl.view.panel, plots)
        child = self.panel.rows[0]
        pane = self.panel.cols[child][0]
        pane.var_view.set("Persistent Histogram")
        self.panel.set_view(None, child, pane)

    # --- GUI bind events and setters --- #
    def handle_event(self, event):
        if event.widget == self.ctrl.view.mode.cl_ent_overlap:
            self.set_overlap(self.ctrl.view.mode.cl_var_overlap.get())

    def set_overlap(self, overlap):
        try:
            overlap = float(overlap)
            self.ctrl.model.mode.set_overlap(overlap)
        except ValueError:
            pass
        self.ctrl.view.mode.cl_var_overlap.set(f"{self.ctrl.model.mode.get_overlap():.2f}")
