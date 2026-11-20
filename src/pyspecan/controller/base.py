"""View independent controller

Owns the model, the plots and playback. A view subclasses `Controller` and only
has to say what it can draw (FEATURES) and what to do with frames (deliver):

    class Controller(_Controller):
        FEATURES = {LINE, SCATTER, IMAGE}
        def deliver(self, frames, status): ...   # {plot id: Frame}

Playback is either threaded (`start_stream`, for event driven views like web / tk) or
driven by the view calling `tick()` (console).
"""
import datetime as dt
import math
import pathlib
import sys
import threading
import time

from .. import logger
from ..model.model import Model
from ..model.sink.file import FORMATS
from ..obj import Frequency
from ..plots import GLOBAL_SETTINGS, PlotSet, Source, available, layout_from_kwargs, layout
from ..utils import args
from ..plots.frame import Frame, LINE, SCATTER, IMAGE
from ..utils.time import strfmt_td

class ControllerConfig:
    show = 50.0 # [ms] between frames

def args_controller(parser):
    """Options every view's controller takes"""
    ctrl = args.get_group(parser, "Playback")
    ctrl.add_argument("--show", default=ControllerConfig.show, type=float, help="[ms] time between frames")
    return ctrl

class Controller:
    """Parent controller class"""
    FEATURES: set[str] = {LINE, SCATTER, IMAGE}

    def __init__(self, model: Model, view, **kwargs):
        self.log = logger.new(type(self).__module__.rsplit(".", 1)[-1])
        self.model = model
        self.view = view
        self.source = Source(model)
        self.plots = PlotSet(self.source)
        spec = layout_from_kwargs(kwargs)
        layout.validate(spec, self.plot_types)
        self.plots.apply(spec)

        self.lock = threading.RLock() # guards model + plots
        self.playing = False
        self.running = True
        self.message = ""
        self.time_show = float(kwargs.get("show", ControllerConfig.show))
        self.thread: threading.Thread | None = None

    # --- plots --- #
    @property
    def plot_types(self) -> list[str]:
        """Plots this view can draw"""
        return available(self.FEATURES)

    def _check_type(self, name):
        if name not in self.plot_types:
            raise ValueError(f"unknown plot {name!r}")

    def add_plot(self, name: str, row: int | None = None) -> str:
        self._check_type(name)
        return self.plots.add(name, row)

    def del_plot(self, pid: str):
        self.plots.remove(pid)

    def set_plot_type(self, pid: str, name: str):
        self._check_type(name)
        self.plots.retype(pid, name)

    def move_plot(self, pid: str, target: str | None, where: str):
        self.plots.move(pid, target, where)

    def set_plot(self, pid: str, key: str, value):
        """Change a plot setting, plots linked to it (or every plot, for a global) follow"""
        with self.lock:
            self.plots.set(pid, key, value)
            if key != "enabled": # pausing a plot must not draw it
                self.redraw()

    def save_layout(self) -> str:
        """The plots, their settings, links and markers as json, for --layout or load_layout"""
        with self.lock:
            return layout.dumps(self.plots.to_spec())

    def load_layout(self, text: str):
        """Replace the plots by a saved layout (json text), nothing changes when it is invalid"""
        spec = layout.loads(text)
        layout.validate(spec, self.plot_types)
        with self.lock:
            self.plots.apply(spec)
            self.redraw()
        self.state_changed()

    def link_plot(self, pid: str, target: str) -> str:
        """Link `pid` to `target`: they share level / processing settings, the auto ref level and markers"""
        with self.lock:
            lid = self.plots.link(pid, target)
            self.redraw()
        self.state_changed()
        return lid

    def unlink_plot(self, pid: str):
        with self.lock:
            self.plots.unlink(pid)
            self.redraw()
        self.state_changed()

    def _markers(self, pid: str):
        plot = self.plots.get(pid)
        if not plot.MARKERS:
            raise ValueError(f"{plot.NAME} has no markers")
        return plot.markers

    def add_marker(self, pid: str, kind: str, **params) -> str:
        with self.lock:
            mid = self._markers(pid).add(kind, **params)
            self.redraw()
            return mid

    def del_marker(self, pid: str, mid: str):
        with self.lock:
            self._markers(pid).remove(mid)
            self.redraw()

    def set_marker(self, pid: str, mid: str, key: str, value):
        with self.lock:
            self._markers(pid).set(mid, key, value)
            self.redraw()

    def marker_action(self, pid: str, mid: str, action: str):
        """A marker's action (a peak marker's next / prev peak) on the plot's latest trace"""
        with self.lock:
            plot = self.plots.get(pid)
            markers = self._markers(pid)
            if plot.last is None:
                raise ValueError("no trace yet: step or play first")
            markers.act(mid, action, plot, plot.last, plot.bin_freqs(len(plot.last)))
            self.redraw()

    def set_marker_params(self, pid: str, mid: str, values: dict):
        """Several settings of one marker at once, one redraw (a mouse drag edits center and width together)"""
        with self.lock:
            self._markers(pid).set_many(mid, values)
            self.redraw()

    def redraw(self):
        """Draw the current block again, markers edited while stopped would show nothing until the next block"""
        with self.lock:
            if self.playing or self.source.seq == 0: # playing: the next block shows it, nothing read yet: nothing to draw
                return
            self.deliver(self.plots.update(self.log), self.get_status())

    def reset_plots(self):
        with self.lock:
            self.source.reset()
            self.plots.reset()

    # --- view hooks --- #
    def deliver(self, frames: dict[str, Frame], status: dict):
        """Show the frames of one tick, runs on the playback thread (or in tick())"""
        raise NotImplementedError()

    def state_changed(self):
        """Something other than frames changed (settings, playing, plots), tell the view"""

    # --- state --- #
    @property
    def sink(self):
        return self.model.sink

    def get_status(self) -> dict:
        """The parts of the state that change while streaming"""
        status = {"playing": self.playing, "message": self.message}
        if self.sink.SEEKABLE:
            status.update({
                "cur_samp": self.sink.cur_samp,
                "time_cur": strfmt_td(dt.timedelta(seconds=self.sink.cur_time())),
            })
        return status

    def get_state(self) -> dict:
        with self.lock:
            sink = self.sink
            state = {
                **self.get_status(),
                "sink": type(sink).__name__,
                "fs": str(sink.get_fs()),
                "cf": str(sink.get_cf()),
                "nfft": self.model.get_nfft(),
                "nfft_exp": int(math.log2(self.model.get_nfft())),
                "overlap": self.model.get_overlap(),
                "block_size": self.model.get_block_size(),
                "sweep": round(self.model.get_sweep_time(), 3),
                "sweep_samples": self.model.get_sweep_samples(),
                "show": self.time_show,
                "plot_types": self.plot_types,
                **self.plots.describe(),
            }
            radio = sink.status()
            if radio is not None:
                state["radio"] = radio
            if sink.SEEKABLE:
                state.update({
                    "path": str(sink.get_path() or ""),
                    "fmt": sink.get_fmt().name,
                    "formats": FORMATS,
                    "max_samp": sink.max_samp,
                    "time_tot": strfmt_td(dt.timedelta(seconds=sink.tot_time())),
                })
            return state

    # --- commands --- #
    def command(self, cmd: str):
        self.log.trace("command(%s)", cmd)
        if cmd == "stop":
            # not under the lock: the playback thread holds it for a whole block (a persistence plot takes long),
            # and waiting for it here freezes a view that calls this from its event loop. The flag is all it needs,
            # the block in flight finishes and the next tick sees it
            self.playing = False
            return
        with self.lock:
            if cmd == "start":
                if not self.sink.ready():
                    raise ValueError("no file selected" if self.sink.SEEKABLE else "no device")
                self.playing = True
                self.message = ""
            elif cmd == "stop":
                self.playing = False
            elif cmd == "reset":
                self.playing = False
                self.model.reset()
                self.reset_plots()
                self.message = ""
            elif cmd in ("claim", "release", "reconnect"):
                self._need_radio()
                self.playing = False
                if cmd == "reconnect":
                    self.sink.reconnect()
                    self.reset_plots()
                elif cmd == "claim":
                    self.sink.claim_control()
                    self.reset_plots()
                else:
                    self.sink.release_control()
                self.message = f"{self.sink.status()['control']}: {self.sink.name}"
                self.state_changed()
            elif cmd in ("next", "prev"):
                if not self.sink.ready():
                    raise ValueError("no file selected" if self.sink.SEEKABLE else "no device")
                if cmd == "prev" and not self.sink.SEEKABLE:
                    raise ValueError("sink does not support going back")
                self.playing = False
                self.message = "" if self.step(cmd == "next") else "END"
            else:
                raise ValueError(f"unknown command {cmd!r}")

    def setting(self, key: str, value):
        self.log.trace("setting(%s, %s)", key, value)
        with self.lock:
            if key in ("fs", "cf"):
                asked = Frequency.get(value)
                (self.model.set_fs if key == "fs" else self.model.set_cf)(value)
                self.reset_plots() # the carried samples and what was averaged are from the old tuning
                got = (self.model.get_fs() if key == "fs" else self.model.get_cf())
                # the radio decides what it can do (pysdrlib clamps and snaps), say so instead of looking like it took it
                self.message = "" if got.raw == asked.raw else f"{key} is {got} ({asked} is not available)"
            elif key == "device":
                self._need_radio()
                self.playing = False
                self.sink.set_device(value)
                self.reset_plots()
                self.message = f"{self.sink.status()['control']}: {self.sink.name}"
                self.state_changed()
            elif key == "antenna":
                self._need_radio()
                self.sink.set_antenna(value)
                self.reset_plots() # a chain with another converter retunes it
                self.message = f"antenna {value}"
                self.state_changed()
            elif key == "nfft_exp":
                exp = int(value)
                if not 2 <= exp <= 20:
                    raise ValueError("nfft exponent must be 2-20")
                self.model.set_nfft(2**exp)
                self.reset_plots()
            elif key == "overlap":
                self.model.set_overlap(value)
                self.reset_plots()
            elif key == "sweep":
                self.model.set_sweep_time(float(value))
                self.reset_plots()
            elif key == "show":
                self.time_show = max(float(value), 0.0)
            elif key == "samp":
                self._need_file()
                self.playing = False
                self.sink.seek(int(value))
                self.source.reset()
            elif key == "path":
                self.set_path(value)
            elif key in {g.key for g in GLOBAL_SETTINGS}:
                self.plots.set_global(key, value)
                self.redraw()
            elif key == "fmt":
                self._need_file()
                if value not in FORMATS:
                    raise ValueError(f"unknown format {value!r}")
                self.playing = False
                self.sink.set_fmt(value)
                self.sink.reset()
                self.reset_plots()
            else:
                raise ValueError(f"unknown setting {key!r}")

    def _need_radio(self):
        if self.sink.status() is None:
            raise ValueError("the sink is a file, there is no radio")

    def radios(self) -> list[dict]:
        """Radios that can be picked, a server that is down does not get in the way"""
        return self.sink.radios() if self.sink.status() is not None else []

    def _need_file(self):
        if not self.sink.SEEKABLE:
            raise ValueError("sink does not support seeking")

    def set_path(self, value):
        """Open a file, views can restrict where files may come from"""
        self._need_file()
        path = pathlib.Path(str(value)).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"not a file: {path}")
        self.playing = False
        self.sink.set_path(path)
        self.reset_plots()
        self.message = ""

    # --- playback --- #
    def step(self, forward=True) -> bool:
        """Read one block and run the plots on it, returns False if no data was available"""
        sink = self.sink
        count = self.model.get_block_size()
        if not forward:
            self.source.reset() # the carried samples are no longer adjacent
        valid = sink.next(count) if forward else sink.prev(count)
        if not valid:
            return False
        if sink.take_retuned(): # a radio controlled elsewhere was retuned: what was carried is from the old tuning
            self.source.reset()
            self.plots.reset()
            self.state_changed()
        self.source.tick()
        self.deliver(self.plots.update(self.log), self.get_status())
        return True

    def tick(self) -> bool:
        """One playback step paced to `show`, returns False when playback stopped (end of data, error)"""
        t0 = time.perf_counter()
        with self.lock:
            if not self.playing:
                return False
            try:
                valid = self.step()
                if not valid:
                    self.message = "END"
                elif self.message == "END":
                    self.message = ""
            except Exception as e: # keep playback alive
                self.report_error("playback failed", e)
                valid = False
            if not valid:
                self.playing = False
        if not valid:
            self.state_changed()
            return False
        wait = self.time_show/1000 - (time.perf_counter() - t0)
        if wait > 0:
            time.sleep(wait)
        return True

    def report_error(self, what: str, error: Exception):
        """Failures must not be silent: the logger is off by default, so also print to stderr"""
        import traceback
        traceback.print_exception(error, file=sys.stderr)
        self.log.error("%s: %s", what, error)
        self.message = f"ERROR: {type(error).__name__}: {error}"

    def _stream(self):
        while self.running:
            if not self.playing or not self.can_stream():
                time.sleep(0.05)
                continue
            self.tick()

    def can_stream(self) -> bool:
        """Views with nobody to show frames to (no browser connected) pause playback"""
        return True

    def start_stream(self):
        self.thread = threading.Thread(target=self._stream, name="stream", daemon=True)
        self.thread.start()

    QUIT_WAIT = 3.0 # [s] the stream thread gets to finish its block (a radio read waits at most 2 s) before the sink closes

    def quit(self):
        self.running = False
        self.playing = False
        t = self.thread
        if t is not None and t is not threading.current_thread() and t.is_alive():
            t.join(timeout=self.QUIT_WAIT) # closing the radio under a read in progress would fail that read
        try:
            self.sink.close() # a radio on a server is detached from, not left streaming
        except Exception as e:
            self.log.warning("closing the sink: %s", e)
