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
from ..model.sink.file import Format
from ..obj import Frequency
from ..plots import PlotSet, Source, available, plot_kwargs
from ..plots.frame import Frame, LINE, SCATTER, IMAGE
from ..utils.time import strfmt_td

class ControllerConfig:
    show = 50.0 # [ms] between frames

class Controller:
    """Parent controller class"""
    FEATURES: set[str] = {LINE, SCATTER, IMAGE}

    def __init__(self, model: Model, view, **kwargs):
        self.log = logger.new(type(self).__module__.rsplit(".", 1)[-1])
        self.model = model
        self.view = view
        self.source = Source(model)
        self.plots = PlotSet(self.source, **plot_kwargs(kwargs))

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
        with self.lock:
            self.plots.get(pid).set(key, value)

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
            if sink.SEEKABLE:
                state.update({
                    "path": str(sink.get_path() or ""),
                    "fmt": sink.get_fmt().name,
                    "formats": Format.choices(),
                    "max_samp": sink.max_samp,
                    "time_tot": strfmt_td(dt.timedelta(seconds=sink.tot_time())),
                })
            return state

    # --- commands --- #
    def command(self, cmd: str):
        self.log.trace("command(%s)", cmd)
        with self.lock:
            if cmd == "start":
                if not self.sink.ready():
                    raise ValueError("no file selected" if self.sink.SEEKABLE else "no device")
                self.playing = True
            elif cmd == "stop":
                self.playing = False
            elif cmd == "reset":
                self.playing = False
                self.model.reset()
                self.reset_plots()
                self.message = ""
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
            if key == "fs":
                Frequency.get(value)
                self.model.set_fs(value)
                self.reset_plots()
            elif key == "cf":
                Frequency.get(value)
                self.model.set_cf(value)
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
            elif key == "fmt":
                self._need_file()
                if value not in Format.choices():
                    raise ValueError(f"unknown format {value!r}")
                self.playing = False
                self.sink.set_fmt(value)
                self.sink.reset()
                self.reset_plots()
            else:
                raise ValueError(f"unknown setting {key!r}")

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
                self.message = "" if valid else "END"
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

    def quit(self):
        self.running = False
        self.playing = False
