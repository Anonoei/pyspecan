"""WEB Controller

Owns the model and all logic. The browser is a thin view: it receives `state`
and `frame` messages over a websocket and sends back `cmd`/`set` messages.
"""
import datetime as dt
import itertools
import json
import math
import pathlib
import threading
import time

from fastapi import WebSocket, WebSocketDisconnect

from ... import logger
from ...utils import args
from ...utils.time import strfmt_td
from ...utils.window import WindowLUT
from ...model.model import Model
from ...model.sink.file import Format
from ...obj import Frequency
from ..base import Controller as _Controller
from ...view.WEB.base import View as GUI

from .api import API
from .websocket import WebSocketManager
from .plots import plots as PLOTS
from .plots.base import _Plot
from .plots.psd import PlotConfig

class ControllerConfig:
    show = 50.0

def _ref_level(val):
    return "auto" if str(val).lower() == "auto" else float(val)

def args_ctrl(parser):
    ctrl = args.get_group(parser, "View (WEB)")
    ctrl.add_argument("-p", "--port", type=int, default=8000, help="http port")
    ctrl.add_argument("--host", default="127.0.0.1", help="bind address, use 0.0.0.0 to expose on the network")
    ctrl.add_argument("--root", default=None, help="restrict the browser's file picker to this directory")
    ctrl.add_argument("--show", default=ControllerConfig.show, type=float, help="[ms] time between frames")
    ctrl.add_argument("-rl", "--ref_level", default=PlotConfig.ref_level, type=_ref_level, help="ref level (number or 'auto')")
    ctrl.add_argument("-sd", "--scale_div", default=PlotConfig.scale_div, type=float, help="scale per division")
    ctrl.add_argument("-vb", "--vbw", default=PlotConfig.vbw, type=float, help="video bandwidth")
    ctrl.add_argument("-w", "--window", default=PlotConfig.window, choices=list(WindowLUT.keys()), help="FFT window function")
    return ctrl

class Controller(_Controller):
    """WEB Controller"""
    def __init__(self, model: Model, view: GUI, **kwargs):
        self.log = logger.new("web")
        super().__init__(model, view)
        self.view: GUI = self.view # type hints

        self.lock = threading.RLock() # guards model + plot
        self.playing = False
        self.running = True
        self.time_show = float(kwargs.get("show", ControllerConfig.show))
        self.message = ""
        self.last_frame_time = 0.0
        self.root = pathlib.Path(kwargs["root"]).resolve() if kwargs.get("root") else None
        self.plot_args = {k: kwargs[k] for k in ("ref_level", "scale_div", "vbw", "window") if k in kwargs}
        self.plots: dict[str, _Plot] = {}
        self.plot_names: dict[str, str] = {} # id -> name in PLOTS
        self.layout: list[list[str]] = [] # rows of plot ids
        self._plot_ids = itertools.count(1)
        self.add_plot("PSD")

        self.ws = WebSocketManager(self)
        self.api = API(self)
        self.setup_routes()

        self.thread = threading.Thread(target=self._stream, name="web-stream", daemon=True)
        self.thread.start()
        self.view.on_quit = self.quit

    def quit(self):
        self.running = False
        self.playing = False

    # --- routes --- #
    def setup_routes(self):
        app = self.view.app
        app.include_router(self.api.router)

        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            client_id = await self.ws.connect(websocket)
            try:
                await self.ws.send(client_id, {"type": "state", "data": self.get_state()})
                while True:
                    msg = json.loads(await websocket.receive_text())
                    error = self.handle_message(msg)
                    if error:
                        await self.ws.send(client_id, {"type": "error", "data": error})
            except WebSocketDisconnect:
                pass
            finally:
                self.ws.disconnect(client_id)

    # --- plots --- #
    def add_plot(self, name: str, row: int | None = None) -> str:
        """Add a plot in `row` (an existing row index), or in a new row"""
        if name not in PLOTS:
            raise ValueError(f"unknown plot {name!r}")
        pid = f"p{next(self._plot_ids)}"
        with self.lock:
            self.plots[pid] = PLOTS[name](self, **self.plot_args)
            self.plot_names[pid] = name
            if row is not None and 0 <= row < len(self.layout):
                self.layout[row].append(pid)
            else:
                self.layout.append([pid])
        return pid

    def del_plot(self, pid: str):
        with self.lock:
            if pid not in self.plots:
                raise ValueError(f"unknown plot {pid!r}")
            del self.plots[pid], self.plot_names[pid]
            self.layout = [row for row in ([i for i in row if i != pid] for row in self.layout) if row]

    def set_plot_type(self, pid: str, name: str):
        with self.lock:
            if pid not in self.plots:
                raise ValueError(f"unknown plot {pid!r}")
            if name not in PLOTS:
                raise ValueError(f"unknown plot {name!r}")
            enabled = self.plots[pid].enabled
            self.plots[pid] = PLOTS[name](self, **self.plot_args)
            self.plots[pid].enabled = enabled
            self.plot_names[pid] = name

    def reset_plots(self):
        for plot in self.plots.values():
            plot.reset()

    # --- file browser --- #
    def _allowed(self, path: pathlib.Path) -> bool:
        return self.root is None or path == self.root or self.root in path.parents

    def list_dir(self, path: str | None) -> dict:
        """List a directory for the file picker, defaults to the current file's directory"""
        with self.lock:
            cur = self.model.sink.get_path()
        if not path:
            path = str(pathlib.Path(cur).parent) if cur else (str(self.root) if self.root else ".")
        d = pathlib.Path(path).expanduser().resolve()
        if not d.is_dir():
            d = d.parent
        if not self._allowed(d):
            raise ValueError("path is outside the allowed root")
        entries = []
        try:
            for e in d.iterdir():
                if e.name.startswith("."):
                    continue
                try:
                    is_dir = e.is_dir()
                    entries.append({"name": e.name, "dir": is_dir, "size": 0 if is_dir else e.stat().st_size})
                except OSError:
                    continue
        except PermissionError:
            raise ValueError("permission denied")
        entries.sort(key=lambda e: (not e["dir"], e["name"].lower()))
        parent = d.parent if d.parent != d and self._allowed(d.parent) else None
        return {"path": str(d), "parent": str(parent) if parent else None, "entries": entries}

    # --- state --- #
    def get_status(self) -> dict:
        """The parts of the state that change while streaming"""
        sink = self.model.sink
        status = {"playing": self.playing, "message": self.message}
        if hasattr(sink, "max_samp"): # FILE sink
            status.update({
                "cur_samp": sink.cur_samp,
                "time_cur": strfmt_td(dt.timedelta(seconds=sink.cur_time())),
            })
        return status

    def get_state(self) -> dict:
        with self.lock:
            sink = self.model.sink
            state = {
                **self.get_status(),
                "sink": type(sink).__name__,
                "fs": str(sink.get_fs()),
                "cf": str(sink.get_cf()),
                "nfft": self.model.get_nfft(),
                "nfft_exp": int(math.log2(self.model.get_nfft())),
                "block_size": self.model.get_block_size(),
                "sweep": self.model.get_sweep_time(),
                "sweep_samples": self.model.get_sweep_samples(),
                "show": self.time_show,
                "layout": self.layout,
                "plots": {pid: {
                    "name": self.plot_names[pid], "title": plot.TITLE,
                    "fields": plot.fields(), "settings": plot.settings(),
                } for pid, plot in self.plots.items()},
                "plot_types": list(PLOTS.keys()),
            }
            if hasattr(sink, "max_samp"):
                state.update({
                    "path": str(sink.get_path() or ""),
                    "fmt": sink.get_fmt().name,
                    "formats": Format.choices(),
                    "max_samp": sink.max_samp,
                    "time_tot": strfmt_td(dt.timedelta(seconds=sink.tot_time())),
                })
            return state

    def push_state(self):
        self.ws.publish({"type": "state", "data": self.get_state()})

    # --- client messages --- #
    def handle_message(self, msg: dict):
        """Apply a client message, returns an error string on failure"""
        try:
            kind = msg.get("type")
            if kind == "cmd":
                self.command(msg["cmd"])
            elif kind == "set":
                self.setting(msg["key"], msg.get("value"))
            elif kind == "plot":
                self.plot_command(msg["op"], msg)
            else:
                return f"unknown message type {kind!r}"
        except (ValueError, KeyError, TypeError, OSError) as e:
            self.log.debug("bad message %s: %s", msg, e)
            self.push_state() # resync the client's inputs
            return f"{type(e).__name__}: {e}"
        self.push_state()
        return None

    def plot_command(self, op: str, msg: dict):
        self.log.trace("plot_command(%s, %s)", op, msg)
        with self.lock:
            if op == "add":
                self.add_plot(msg["name"], msg.get("row"))
            elif op == "del":
                self.del_plot(msg["id"])
            elif op == "type":
                self.set_plot_type(msg["id"], msg["name"])
            elif op == "set":
                plot = self.plots.get(msg["id"])
                if plot is None:
                    raise ValueError(f"unknown plot {msg['id']!r}")
                plot.set(msg["key"], msg.get("value"))
            else:
                raise ValueError(f"unknown plot op {op!r}")

    def command(self, cmd: str):
        self.log.trace("command(%s)", cmd)
        with self.lock:
            if cmd == "start":
                if self.model.sink.get_path() is None:
                    raise ValueError("no file selected")
                self.playing = True
            elif cmd == "stop":
                self.playing = False
            elif cmd == "reset":
                self.playing = False
                self.model.reset()
                self.reset_plots()
                self.message = ""
            elif cmd in ("next", "prev"):
                if self.model.sink.get_path() is None:
                    raise ValueError("no file selected")
                self.playing = False
                self.message = "" if self._step(cmd == "next") else "END"
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
                self.model.set_block_size(2**exp)
                self.reset_plots()
            elif key == "sweep":
                self.model.set_sweep_time(float(value))
            elif key == "show":
                self.time_show = max(float(value), 0.0)
            elif key == "samp":
                if not hasattr(self.model.sink, "max_samp"):
                    raise ValueError("sink does not support seeking")
                self.playing = False
                self.model.sink.dev.cur_samp = max(0, min(int(value), self.model.sink.max_samp))
            elif key == "path":
                self.set_path(value)
            elif key == "fmt":
                if value not in Format.choices():
                    raise ValueError(f"unknown format {value!r}")
                self.playing = False
                self.model.sink.set_fmt(value)
                self.model.sink.reset()
                self.reset_plots()
            else:
                raise ValueError(f"unknown setting {key!r}")

    def set_path(self, value):
        path = pathlib.Path(str(value)).expanduser().resolve()
        if not self._allowed(path):
            raise ValueError("path is outside the allowed root")
        if not path.is_file():
            raise ValueError(f"not a file: {path}")
        self.playing = False
        self.model.sink.set_path(path)
        self.reset_plots()
        self.message = ""

    # --- streaming --- #
    def _step(self, forward=True) -> bool:
        """Read one block and publish a frame, returns False if no data was available"""
        sink = self.model.sink
        count = self.model.get_block_size()
        valid = sink.next(count) if forward else sink.prev(count)
        if not valid:
            return False
        frames = {}
        for pid, plot in self.plots.items():
            t0 = time.perf_counter()
            try:
                frame = plot.update(sink.samples)
            except Exception: # one broken plot shouldn't stop the others
                self.log.exception("plot %s failed", pid)
                continue
            if frame is not None:
                frame["ptime"] = time.perf_counter() - t0
                frames[pid] = frame
        self.ws.publish({"type": "frame", "data": {"plots": frames, "status": self.get_status()}})
        return True

    def _stream(self):
        while self.running:
            if not self.playing or not self.ws.connections:
                time.sleep(0.05)
                continue
            t0 = time.perf_counter()
            with self.lock:
                if not self.playing: # stopped while waiting for the lock
                    continue
                try:
                    valid = self._step()
                    self.message = "" if valid else "END"
                except Exception: # keep the thread alive
                    self.log.exception("stream failure")
                    self.message = "ERROR"
                    valid = False
                if not valid:
                    self.playing = False
            if not valid:
                self.push_state()
                continue
            wait = self.time_show/1000 - (time.perf_counter() - t0)
            if wait > 0:
                time.sleep(wait)
