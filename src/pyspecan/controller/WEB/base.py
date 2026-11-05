"""WEB Controller

The browser is a thin view: it receives `state` and `frame` messages over a
websocket and sends back `cmd` / `set` / `plot` messages. Everything else
(plots, playback, settings) lives in the shared controller core.
"""
import json
import pathlib

from fastapi import WebSocket, WebSocketDisconnect

from ...utils import args
from ...model.model import Model
from ...plots import colormap
from ...plots.frame import Frame, LINE, SCATTER, IMAGE
from ...view.WEB.base import View as GUI
from ..base import Controller as _Controller, ControllerConfig

from .api import API
from .websocket import WebSocketManager

def args_ctrl(parser):
    ctrl = args.get_group(parser, "View (WEB)")
    ctrl.add_argument("-p", "--port", type=int, default=8000, help="http port")
    ctrl.add_argument("--host", default="127.0.0.1", help="bind address, use 0.0.0.0 to expose on the network")
    ctrl.add_argument("--root", default=None, help="restrict the browser's file picker to this directory")
    ctrl.add_argument("--show", default=ControllerConfig.show, type=float, help="[ms] time between frames")
    return ctrl

class Controller(_Controller):
    """WEB Controller"""
    FEATURES = {LINE, SCATTER, IMAGE}

    def __init__(self, model: Model, view: GUI, **kwargs):
        super().__init__(model, view, **kwargs)
        self.view: GUI = self.view # type hints
        self.root = pathlib.Path(kwargs["root"]).resolve() if kwargs.get("root") else None
        self.add_plot("PSD")

        self.ws = WebSocketManager(self)
        self.api = API(self)
        self.setup_routes()

        self.view.on_quit = self.quit
        self.start_stream()

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

    # --- core hooks --- #
    def can_stream(self) -> bool:
        return bool(self.ws.connections)

    def deliver(self, frames: dict[str, Frame], status: dict):
        self.ws.publish({"type": "frame", "data": {
            "plots": {pid: frame.to_dict() for pid, frame in frames.items()},
            "status": status,
        }})

    def state_changed(self):
        self.ws.publish({"type": "state", "data": self.get_state()})

    def get_state(self) -> dict:
        state = super().get_state()
        state["colormaps"] = {name: colormap.STOPS[name] for name in colormap.names()}
        return state

    # --- file browser --- #
    def _allowed(self, path: pathlib.Path) -> bool:
        return self.root is None or path == self.root or self.root in path.parents

    def set_path(self, value):
        if not self._allowed(pathlib.Path(str(value)).expanduser().resolve()):
            raise ValueError("path is outside the allowed root")
        super().set_path(value)

    def list_dir(self, path: str | None) -> dict:
        """List a directory for the file picker, defaults to the current file's directory"""
        with self.lock:
            cur = self.sink.get_path() if self.sink.SEEKABLE else None
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
            self.state_changed() # resync the client's inputs
            return f"{type(e).__name__}: {e}"
        self.state_changed()
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
                self.set_plot(msg["id"], msg["key"], msg.get("value"))
            else:
                raise ValueError(f"unknown plot op {op!r}")
