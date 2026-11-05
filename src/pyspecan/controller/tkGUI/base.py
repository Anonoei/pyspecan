"""tkGUI Controller

Binds the tk widgets to the shared controller core. Plots are drawn by `PlotPane`,
frames reach the main thread through a queue (tk widgets must not be touched from
the playback thread).
"""
import collections
import math
import threading
import time
import tkinter as tk

from ... import logger
from ...utils import args
from ..base import Controller as _Controller, ControllerConfig
from ...model.model import Model
from ...plots.frame import Frame, LINE, SCATTER, IMAGE, THREE_D
from ...view.tkGUI.base import View as GUI

from ...backend.tk import theme as theme_tk

from .panels import PanelController
from .sink import Sink

POLL = 20 # [ms] between checks for new frames

class TkConfig:
    theme = "Dark"

def args_ctrl(parser):
    ctrl = args.get_group(parser, "View (tkGUI)")
    ctrl.add_argument("--theme", default=TkConfig.theme, choices=[k for k in theme_tk.theme.keys()])
    ctrl.add_argument("--show", default=ControllerConfig.show, type=float, help="[ms] time between frames")
    return ctrl

class Controller(_Controller):
    """tkGUI Controller"""
    FEATURES = {LINE, SCATTER, IMAGE, THREE_D}

    def __init__(self, model: Model, view: GUI, sink, **kwargs):
        super().__init__(model, view, **kwargs)
        self.log = logger.new("tkGUI")
        self.view: GUI = self.view # type hints
        self.sink_ui: Sink = sink(self)
        self._queue: collections.deque = collections.deque(maxlen=64)
        self._queue_lock = threading.Lock()
        self._message_until = 0.0
        self._polling = False

        v = self.view
        v.tb_btn_start.config(command=self.sink_ui.start)
        v.tb_btn_stop.config(command=self.sink_ui.stop)
        v.tb_btn_reset.config(command=self.sink_ui.reset)
        for entry, key in (
            (v.tb_ent_sweep, "sweep"), (v.tb_ent_show, "show"), (v.cl_ent_fs, "fs"), (v.cl_ent_cf, "cf"),
            (v.cl_ent_nfft_exp, "nfft_exp"), (v.cl_ent_overlap, "overlap"),
        ):
            entry.bind("<Return>", lambda e, k=key: self.commit(k))

        style = kwargs.get("theme", TkConfig.theme)
        theme_tk.get(style)(self.view.root) # pyright: ignore[reportCallIssue]

        self.panels = PanelController(self, self.view.panel)
        pane = self.panels.cols[self.panels.rows[0]][0]
        self.panels.set_view(self.panels.rows[0], pane, "Persistence" if kwargs.get("mode") == "rt" else "PSD")

        self.refresh()
        self.view.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.start_stream()
        self.view.root.after(POLL, self._poll)

    # --- core hooks --- #
    def deliver(self, frames: dict[str, Frame], status: dict):
        """Runs on the playback thread"""
        with self._queue_lock:
            self._queue.append(frames)

    def reset_plots(self):
        super().reset_plots()
        with self._queue_lock:
            self._queue.clear()
        self.panels.on_reset()

    def _poll(self):
        """Main thread: draw what the playback thread produced, follow its state"""
        if not self.running or self._polling:
            return
        # drawing flushes the event loop (blitting), so other callbacks run in the middle of it,
        # including one that closes the window. Don't re-enter, and ignore widgets that went away.
        self._polling = True
        try:
            with self._queue_lock:
                queued = list(self._queue)
                self._queue.clear()
            if queued:
                t0 = time.perf_counter()
                for frames in queued:
                    self.panels.push(frames)
                self.panels.render()
                self.view.tb_var_draw_time.set(f"{time.perf_counter() - t0:06.3f}s")
            self.draw_tb()
            self.view.root.after(POLL, self._poll)
        except tk.TclError:
            if self.running:
                raise
        finally:
            self._polling = False

    # --- widgets <- state --- #
    def show_message(self, text: str, seconds=4.0):
        self._message_until = time.monotonic() + seconds
        self.view.tb_lbl_msg.configure(text=text)

    def draw_tb(self):
        v = self.view
        status = self.get_status()
        v.tb_btn_start.config(state="disabled" if status["playing"] else "normal")
        v.tb_btn_stop.config(state="normal" if status["playing"] else "disabled")
        if time.monotonic() >= self._message_until:
            v.tb_lbl_msg.configure(text=status["message"])
        self.sink_ui.draw_tb(status)

    def refresh(self):
        """Show the model's settings in the widgets"""
        v, m = self.view, self.model
        v.tb_var_sweep.set(f"{m.get_sweep_time():02.3f}")
        v.tb_var_show.set(f"{self.time_show:02.3f}")
        v.cl_var_fs.set(str(m.get_fs()))
        v.cl_var_cf.set(str(m.get_cf()))
        v.cl_var_nfft_exp.set(str(int(math.log2(m.get_nfft()))))
        v.cl_lbl_nfft.config(text=str(m.get_nfft()))
        v.cl_var_overlap.set(f"{m.get_overlap():.2f}")
        v.cl_lbl_block_size.configure(text=str(m.get_block_size()))
        v.cl_lbl_sweep_samples.configure(text=str(m.get_sweep_samples()))
        self.sink_ui.draw_cl()
        self.draw_tb()

    # --- widgets -> state --- #
    def apply_setting(self, key, value):
        """Change a setting, errors go to the message label instead of the console"""
        try:
            self.setting(key, value)
        except (ValueError, OSError) as e:
            self.show_message(str(e))
        self.refresh()

    def run_command(self, cmd):
        try:
            self.command(cmd)
        except (ValueError, OSError) as e:
            self.show_message(str(e))
        self.draw_tb()

    def commit(self, key):
        v = self.view
        var = {"sweep": v.tb_var_sweep, "show": v.tb_var_show, "fs": v.cl_var_fs, "cf": v.cl_var_cf,
               "nfft_exp": v.cl_var_nfft_exp, "overlap": v.cl_var_overlap}[key]
        self.apply_setting(key, var.get())

    def quit(self):
        super().quit()
        if self.thread is not None:
            self.thread.join(timeout=1)
        self.view.root.quit()
        self.view.root.destroy()
