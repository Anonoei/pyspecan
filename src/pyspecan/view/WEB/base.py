"""Create a WEB view"""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

from ..base import View as _View

class View(_View):
    """WEB view class, serves the page and static files"""
    def __init__(self, **kwargs):
        self.host = kwargs.get("host", "127.0.0.1")
        self.port = int(kwargs.get("port", 8000))
        self.on_quit = None

        path = Path(__file__).parent
        self.app = FastAPI(title="pyspecan")
        self.app.mount("/static", StaticFiles(directory=path / "static"), name="static")
        self.templates = Jinja2Templates(directory=path / "templates")

        @self.app.get("/", response_class=HTMLResponse)
        async def index(request: Request):
            return self.templates.TemplateResponse(request, "index.html")

    def mainloop(self):
        print(f"pyspecan web view: http://{self.host}:{self.port}")
        try:
            uvicorn.run(self.app, host=self.host, port=self.port, log_level="warning")
        finally:
            self.quit()

    def quit(self):
        if self.on_quit is not None:
            self.on_quit()
