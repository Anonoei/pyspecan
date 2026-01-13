"""tkGUI Controller"""
import math

from .dispatch import Dispatch, CMD

from ...utils import args
from ..base import Controller as _Controller

from ... import logger
from ...model.model import Model
from ...obj import Frequency
from ...view.tkGUI.base import View as GUI

from ...backend.mpl.plot import BlitPlot
from ...backend.tk import theme as theme_tk

from .mode import Mode
from .sink import Sink
from .panels import PanelController
from .plot_base import TimePlotController, FreqPlotController, BlitPlot

class ControllerConfig:
    theme = "Dark"
    sweep = 50.0
    show = 50.0

def args_ctrl(parser):
    ctrl = args.get_group(parser, "View (tkGUI)")
    ctrl.add_argument("--theme", default=ControllerConfig.theme, choices=[k for k in theme_tk.theme.keys()])
    ctrl.add_argument("--sweep", default=ControllerConfig.sweep, type=float)
    ctrl.add_argument("--show", default=ControllerConfig.show, type=float)
    return ctrl

class Controller(_Controller):
    """tkGUI Controller"""
    def __init__(self, model: Model, view: GUI, mode, sink, **kwargs):
        self.log = logger.new("tkGUI")
        super().__init__(model, view)
        self.view: GUI = self.view # type hints
        self.dispatch: Dispatch = Dispatch(self)
        self.mode: Mode = mode(self)
        self.sink: Sink = sink(self)

        self.view.tb_btn_start.config(command=self.sink.start)
        self.view.tb_btn_stop.config(command=self.sink.stop)
        self.view.tb_btn_reset.config(command=self.sink.reset)

        self.time_show = kwargs.get("show", ControllerConfig.show)
        self.model.set_sweep_time(kwargs.get("sweep", ControllerConfig.sweep))

        self.nfft_exp = int(math.log2(self.model.get_nfft()))
        self._last_f = None
        self.panel: PanelController = None # type: ignore

        self.view.tb_var_sweep.set(f"{self.model.get_sweep_time():02.3f}")
        self.view.tb_ent_sweep.bind("<Return>", self.handle_event)
        self.view.tb_var_show.set(f"{self.time_show:02.3f}")
        self.view.tb_ent_show.bind("<Return>", self.handle_event)

        self.view.tb_var_draw_time.set(f"{0.0:06.3f}s")
        self.view.tb_btn_start.config(command=self.sink.start)
        self.view.tb_btn_stop.config(command=self.sink.stop)
        self.view.tb_btn_reset.config(command=self.sink.reset)

        self.view.cl_ent_fs.bind("<Return>", self.handle_event)
        self.view.cl_ent_cf.bind("<Return>", self.handle_event)
        self.view.cl_ent_nfft_exp.bind("<Return>", self.handle_event)

        self.dispatch.start()

        style = kwargs.get("theme", ControllerConfig.theme)
        theme_tk.get(style)(self.view.root) # pyright: ignore[reportCallIssue]

        self.set_cf(None)
        self.set_fs(None)
        self.set_nfft(None)

        self.view.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.draw()

    def quit(self):
        self.dispatch.stop()
        self.view.root.quit()
        self.view.root.destroy()

    def draw(self):
        self.draw_tb()
        self.draw_cl()
        self.draw_view()

    def draw_tb(self):
        # self.view.var_sweep.set(f"{self.model.get_sweep_time():02.3f}")
        # self.view.var_show.set(f"{self.time_show:02.3f}")
        self.sink.draw_tb()
        self.mode.draw_tb()

    def draw_cl(self):
        # self.view.var_fs.set(str(self.model.get_fs()))
        # self.view.var_cf.set(str(self.model.get_cf()))
        # self.view.lbl_nfft.configure(text=str(self.model.get_nfft()))
        # self.view.var_nfft_exp.set(str(self.nfft_exp))
        self.view.cl_lbl_block_size.configure(text=str(self.model.get_block_size()))
        self.view.cl_lbl_sweep_samples.configure(text=str(self.model.get_sweep_samples()))
        self.sink.draw_cl()
        self.mode.draw_cl()

    def draw_view(self):
        pass

    # --- GUI bind events and setters --- #
    def handle_event(self, event):
        if event.widget == self.view.tb_ent_sweep:
            self.set_time_sweep(self.view.tb_var_sweep.get())
        elif event.widget == self.view.tb_ent_show:
            self.set_time_show(self.view.tb_var_show.get())
        elif event.widget == self.view.cl_ent_fs:
            self.set_fs(self.view.cl_var_fs.get())
        elif event.widget == self.view.cl_ent_cf:
            self.set_cf(self.view.cl_var_cf.get())
        elif event.widget == self.view.cl_ent_nfft_exp:
            self.set_nfft(self.view.cl_var_nfft_exp.get())

    def set_time_sweep(self, ts):
        self.log.trace("set_time_sweep(%s)", ts)
        try:
            self.model.set_sweep_time(float(ts))
        except ValueError:
            pass
        self.view.tb_var_sweep.set(f"{self.model.get_sweep_time():02.3f}")
        self.draw_cl()
    def set_time_show(self, ts):
        self.log.trace("set_time_show(%s)", ts)
        try:
            ts = float(ts)
            self.time_show = ts
        except ValueError:
            pass
        self.view.tb_var_show.set(f"{self.time_show:02.3f}")

    def set_fs(self, fs):
        self.log.trace("set_fs(%s)", fs)
        if not fs is None:
            try:
                Frequency.get(fs)
                self.model.set_fs(fs)
                self.dispatch.send(CMD.UPDATE_FS)
                self.dispatch.send(CMD.UPDATE_F)
            except ValueError:
                pass
        self.view.cl_var_fs.set(str(self.model.sink.get_fs()))
        self.draw_tb()
        self.draw_cl()
    def set_cf(self, cf):
        self.log.trace("set_cf(%s)", cf)
        if not cf is None:
            try:
                Frequency.get(cf)
                self.model.set_cf(cf)
                self.dispatch.send(CMD.UPDATE_F)
            except ValueError:
                pass
        self.view.cl_var_cf.set(str(self.model.sink.get_cf()))
        self.draw_cl()
    def set_nfft(self, exp):
        self.log.trace("set_nfft(%s)", exp)
        if not exp is None:
            try:
                exp = int(exp)
                self.nfft_exp = exp
                self.model.set_nfft(2**exp)
            except ValueError:
                pass
        self.view.cl_var_nfft_exp.set(str(self.nfft_exp))
        self.view.cl_lbl_nfft.config(text=str(self.model.get_nfft()))
        self.dispatch.send(CMD.UPDATE_NFFT)
        self.dispatch.send(CMD.UPDATE_F)
        self.draw_cl()
