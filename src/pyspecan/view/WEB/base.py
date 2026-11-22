"""Create a WEB view"""
import asyncio
import logging
import socket
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ... import logger
from ..base import View as _View


def _quiet_resets(loop: asyncio.AbstractEventLoop, context: dict):
    """A browser closing its connection is normal. On Windows before Python 3.13 the proactor loop logs a
    ConnectionResetError traceback for it (CPython bpo-39010), drop those and pass anything else on"""
    if isinstance(context.get("exception"), ConnectionResetError):
        return
    loop.default_exception_handler(context)

@asynccontextmanager
async def _lifespan(_app):
    if sys.platform == "win32":
        asyncio.get_running_loop().set_exception_handler(_quiet_resets)
    yield


class View(_View):
    """WEB view class, serves the page and static files"""
    def __init__(self, **kwargs):
        self.host = kwargs.get("host", "127.0.0.1")
        self.port = int(kwargs.get("port", 8000))
        self.on_quit = None
        self.log = logger.new("web")

        path = Path(__file__).parent
        self.app = FastAPI(title="pyspecan", lifespan=_lifespan)
        self.app.mount("/static", StaticFiles(directory=path / "static"), name="static")
        self.templates = Jinja2Templates(directory=path / "templates")

        @self.app.get("/", response_class=HTMLResponse)
        async def index(request: Request):
            return self.templates.TemplateResponse(request, "index.html")

    def urls(self) -> list[str]:
        """Where a browser finds the page: the bind address, or for every interface (0.0.0.0, ::) this machine by
        name and by its address on the network"""
        if self.host not in ("0.0.0.0", "::", ""):
            return [f"http://{self.host}:{self.port}"]
        hosts = ["127.0.0.1", socket.gethostname()]
        try: # the address a route out uses (nothing is sent: connect on UDP only picks the interface)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("192.0.2.1", 9)) # TEST-NET-1, never routed anywhere real
                hosts.append(s.getsockname()[0])
        except OSError:
            pass
        return [f"http://{h}:{self.port}" for h in dict.fromkeys(hosts)]

    def mainloop(self):
        urls = self.urls()
        level = logger.console_level()
        if level is None or level > logging.INFO: # where to point the browser, whatever the log shows
            print(f"pyspecan web view: {', '.join(urls)}", flush=True)
        where = "every interface" if self.host in ("0.0.0.0", "::", "") else "this address only"
        self.log.info("serving on %s:%s (%s): %s", self.host, self.port, where, ", ".join(urls))
        options = {} if level is None else { # our handlers (logger.setup), not uvicorn's own config
            "log_config": None,
            # uvicorn's lines (every request, every websocket) only from debug on: clients are logged by the controller
            "log_level": "debug" if level <= logging.DEBUG else "warning",
            "access_log": level <= logging.DEBUG,
        }
        try:
            uvicorn.run(self.app, host=self.host, port=self.port, **({"log_level": "warning"} | options),
                        ws_per_message_deflate=False) # frames come deflated already, once for all clients (see WEB.wire)
        finally:
            self.quit()

    def quit(self):
        if self.on_quit is not None:
            self.on_quit()
