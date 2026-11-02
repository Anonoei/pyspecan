"""WEB Controller

Owns the model and all logic. The browser is a thin view: it receives `state`
and `frame` messages over a websocket and sends back `cmd`/`set` messages.
"""
import datetime as dt
import json
import math
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
from .plots.psd import PSD, PlotConfig

class ControllerConfig:
    show = 50.0

def _ref_level(val):
    return "auto" if str(val).lower() == "auto" else float(val)

def args_ctrl(parser):
    ctrl = args.get_group(parser, "View (WEB)")
    ctrl.add_argument("-p", "--port", type=int, default=8000, help="http port")
    ctrl.add_argument("--host", default="127.0.0.1", help="bind address, use 0.0.0.0 to expose on the network")
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
        self.plot = PSD(self, **{k: kwargs[k] for k in ("ref_level", "scale_div", "vbw", "window") if k in kwargs})

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

    # --- state --- #
    def get_state(self) -> dict:
        with self.lock:
            sink = self.model.sink
            state = {
                "playing": self.playing,
                "message": self.message,
                "sink": type(sink).__name__,
                "fs": str(sink.get_fs()), "fs_raw": sink.get_fs().raw,
                "cf": str(sink.get_cf()), "cf_raw": sink.get_cf().raw,
                "nfft": self.model.get_nfft(),
                "nfft_exp": int(math.log2(self.model.get_nfft())),
                "block_size": self.model.get_block_size(),
                "sweep": self.model.get_sweep_time(),
                "sweep_samples": self.model.get_sweep_samples(),
                "show": self.time_show,
                "plot": self.plot.settings(),
                "windows": list(WindowLUT.keys()),
            }
            if hasattr(sink, "max_samp"): # FILE sink
                state.update({
                    "path": str(sink.get_path()),
                    "fmt": sink.get_fmt().name,
                    "formats": Format.choices(),
                    "cur_samp": sink.cur_samp,
                    "max_samp": sink.max_samp,
                    "time_cur": strfmt_td(dt.timedelta(seconds=sink.cur_time())),
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
            else:
                return f"unknown message type {kind!r}"
        except (ValueError, KeyError, TypeError) as e:
            self.log.debug("bad message %s: %s", msg, e)
            self.push_state() # resync the client's inputs
            return f"{type(e).__name__}: {e}"
        self.push_state()
        return None

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
                self.plot.reset()
                self.message = ""
            elif cmd in ("next", "prev"):
                self.playing = False
                self._step(cmd == "next")
            else:
                raise ValueError(f"unknown command {cmd!r}")

    def setting(self, key: str, value):
        self.log.trace("setting(%s, %s)", key, value)
        with self.lock:
            plot = self.plot
            if key == "fs":
                Frequency.get(value)
                self.model.set_fs(value)
                plot.reset()
            elif key == "cf":
                Frequency.get(value)
                self.model.set_cf(value)
            elif key == "nfft_exp":
                exp = int(value)
                if not 2 <= exp <= 20:
                    raise ValueError("nfft exponent must be 2-20")
                self.model.set_nfft(2**exp)
                self.model.set_block_size(2**exp)
                plot.reset()
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
                self.playing = False
                self.model.sink.set_path(value)
                plot.reset()
            elif key == "fmt":
                if value not in Format.choices():
                    raise ValueError(f"unknown format {value!r}")
                self.model.sink.set_fmt(value)
            elif key == "ref_level":
                plot.set_ref_level(value)
            elif key == "scale_div":
                plot.set_scale(value)
            elif key == "vbw":
                plot.set_vbw(value)
            elif key == "window":
                plot.set_window(value)
            elif key == "show_min":
                plot.show_min = bool(value)
            elif key == "show_max":
                plot.show_max = bool(value)
            elif key == "enabled":
                plot.toggle(value)
            else:
                raise ValueError(f"unknown setting {key!r}")

    # --- streaming --- #
    def _step(self, forward=True) -> bool:
        """Read one block and publish a frame, returns False if no data was available"""
        sink = self.model.sink
        count = self.model.get_block_size()
        valid = sink.next(count) if forward else sink.prev(count)
        if not valid:
            return False
        t0 = time.perf_counter()
        frame = self.plot.update(sink.samples)
        ptime = time.perf_counter() - t0
        if frame is not None:
            frame["ptime"] = ptime
            frame["cf"] = sink.get_cf().raw
            frame["fs"] = sink.get_fs().raw
            self.ws.publish({"type": "frame", "data": frame})
        self.last_frame_time = ptime
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
                    if not valid:
                        self.playing = False
                    self.message = "" if valid else "END"
                except Exception: # keep the thread alive
                    self.log.exception("stream failure")
                    self.playing = False
                    self.message = "ERROR"
                    valid = False
            self.push_state()
            if not valid:
                continue
            wait = self.time_show/1000 - (time.perf_counter() - t0)
            if wait > 0:
                time.sleep(wait)
