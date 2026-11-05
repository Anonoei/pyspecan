"""HTTP API"""
from fastapi import APIRouter, HTTPException

class API:
    def __init__(self, parent):
        self.parent = parent
        self.router = APIRouter(prefix="/api")

        @self.router.get("/status")
        def get_status():
            return {"clients": len(self.parent.ws.connections), "playing": self.parent.playing}

        @self.router.get("/state")
        def get_state():
            return self.parent.get_state()

        @self.router.get("/fs")
        def list_dir(path: str | None = None):
            try:
                return self.parent.list_dir(path)
            except ValueError as e:
                raise HTTPException(400, str(e))
