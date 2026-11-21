"""Create a WEB view"""
import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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

        path = Path(__file__).parent
        self.app = FastAPI(title="pyspecan", lifespan=_lifespan)
        self.app.mount("/static", StaticFiles(directory=path / "static"), name="static")
        self.templates = Jinja2Templates(directory=path / "templates")

        @self.app.get("/", response_class=HTMLResponse)
        async def index(request: Request):
            return self.templates.TemplateResponse(request, "index.html")

    def mainloop(self):
        print(f"pyspecan web view: http://{self.host}:{self.port}")
        try:
            uvicorn.run(self.app, host=self.host, port=self.port, log_level="warning",
                        ws_per_message_deflate=False) # frames come deflated already, once for all clients (see WEB.wire)
        finally:
            self.quit()

    def quit(self):
        if self.on_quit is not None:
            self.on_quit()
