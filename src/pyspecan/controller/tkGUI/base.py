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
from tkinter import ttk

from ... import logger
from ...utils import args, dialog
from ..base import Controller as _Controller
from ...model.model import Model
from ...plots import GLOBAL_SETTINGS
from ...plots.frame import Frame, LINE, SCATTER, IMAGE, THREE_D
from ...view.tkGUI.base import View as GUI, ADD_LABEL

from ...backend.tk import theme as theme_tk

from .panels import PanelController
from .sink import Sink

POLL = 20 # [ms] between checks for new frames
LAYOUT_FILES = [("pyspecan layout", "*.json"), ("All files", "*")]

class TkConfig:
    theme = "Dark"

def args_ctrl(parser):
    ctrl = args.get_group(parser, "View (tkGUI)")
    ctrl.add_argument("--theme", default=TkConfig.theme, choices=[k for k in theme_tk.theme.keys()])
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
        self._dirty = False
        self._deferred: list = []

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

        self.global_vars: dict[str, tk.StringVar] = {}
        self._build_globals()

        self.panels = PanelController(self, self.view.panel)
        v.tb_cb_add.config(values=self.plot_types)
        v.tb_cb_add.bind("<<ComboboxSelected>>", self.add_from_dropdown)
        v.tb_btn_layout_save.config(command=self.save_layout_dialog)
        v.tb_btn_layout_load.config(command=self.load_layout_dialog)
        self.panels.rebuild()

        self.refresh()
        self.view.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.start_stream()
        self._poll_id = self.view.root.after(POLL, self._poll)

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

    def state_changed(self):
        self._dirty = True # the playback thread must not touch widgets, the poll shows it

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
            t0 = time.perf_counter()
            for frames in queued:
                self.panels.push(frames)
            self.panels.render() # also draws panes that were rebuilt and are waiting for their last frame
            if queued:
                self.view.tb_var_draw_time.set(f"{time.perf_counter() - t0:06.3f}s")
            if self._dirty:
                self._dirty = False
                self.refresh() # the radio was retuned elsewhere, or went away
            else:
                self.draw_tb()
            self._poll_id = self.view.root.after(POLL, self._poll)
        except tk.TclError:
            if self.running:
                raise
        finally:
            self._polling = False
            deferred, self._deferred = self._deferred, []
            for fn in deferred:
                fn()

    def _build_globals(self):
        """Settings every plot shares (calibration), one section per group under the source settings"""
        groups: dict[str, list] = {}
        for g in GLOBAL_SETTINGS:
            groups.setdefault(g.group, []).append(g)
        for name, settings in groups.items():
            fr = ttk.LabelFrame(self.view.fr_cl, text=name)
            fr.pack(padx=2, pady=2, fill=tk.X)
            for row, g in enumerate(settings):
                ttk.Label(fr, text=g.label).grid(row=row, column=0, sticky=tk.W)
                var = tk.StringVar(fr)
                ent = ttk.Entry(fr, textvariable=var, width=8)
                ent.grid(row=row, column=1, sticky=tk.E)
                ent.bind("<Return>", lambda e, k=g.key: self.apply_setting(k, self.global_vars[k].get()))
                self.global_vars[g.key] = var

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
        for key, var in self.global_vars.items():
            var.set(str(self.plots.globals[key]))
        if hasattr(self, "panels"):
            self.panels.refresh()
        self.sink_ui.draw_cl()
        self.draw_tb()

    # --- widgets -> state --- #
    def apply_setting(self, key, value):
        """Change a setting, errors go to the message label instead of the console"""
        try:
            self.setting(key, value)
        except Exception as e: # also what the radio library raises (Busy, NotController...)
            self.show_message(str(e))
        self.refresh()

    def run_command(self, cmd):
        try:
            self.command(cmd)
        except Exception as e: # also what the radio library raises (Busy, NotController...)
            self.show_message(str(e))
        self.refresh() # a command can change who controls the radio, and the settings with it

    def when_idle(self, fn):
        """Run `fn` now, or once the drawing in progress is done: drawing runs the event loop, and
        rearranging plots in the middle of it would destroy the widgets being drawn"""
        if self._polling:
            self._deferred.append(fn)
        else:
            fn()

    def save_layout_dialog(self):
        path = dialog.save_file("Save layout", LAYOUT_FILES, ".json")
        if path is None:
            return
        try:
            path.write_text(self.save_layout() + "\n")
        except OSError as e:
            return self.show_message(f"Layout not saved: {e}")
        self.show_message(f"Saved {path.name}")

    def load_layout_dialog(self):
        path = dialog.get_file(False, "Load layout", LAYOUT_FILES)
        if path is None:
            return
        def load():
            try:
                self.load_layout(path.read_text())
            except (OSError, ValueError) as e:
                return self.show_message(f"Layout not loaded: {e}", seconds=8)
            self.panels.keep.clear()
            self.panels.rebuild()
            self.show_message(f"Loaded {path.name}")
        self.when_idle(load) # not in the middle of drawing the panes it replaces

    def add_from_dropdown(self, event=None):
        v = self.view
        name = v.tb_var_add.get()
        v.tb_var_add.set(ADD_LABEL)
        v.root.focus_set()
        if name in self.plot_types:
            self.when_idle(lambda: self.panels.add(name))

    def commit(self, key):
        v = self.view
        var = {"sweep": v.tb_var_sweep, "show": v.tb_var_show, "fs": v.cl_var_fs, "cf": v.cl_var_cf,
               "nfft_exp": v.cl_var_nfft_exp, "overlap": v.cl_var_overlap}[key]
        self.apply_setting(key, var.get())

    def quit(self):
        super().quit()
        if self.thread is not None:
            self.thread.join(timeout=1)
        try:
            self.view.root.after_cancel(self._poll_id)
        except (tk.TclError, AttributeError):
            pass
        self.view.root.quit()
        self.view.root.destroy()
