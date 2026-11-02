"""HTTP API"""
from fastapi import APIRouter

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
