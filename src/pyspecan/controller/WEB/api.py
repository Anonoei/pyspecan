"""HTTP API"""
from fastapi import APIRouter, HTTPException, Response


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

        @self.router.get("/layout")
        def get_layout():
            """The plots as a --layout file"""
            return Response(self.parent.save_layout(), media_type="application/json",
                            headers={"Content-Disposition": 'attachment; filename="pyspecan-layout.json"'})

        @self.router.get("/radios")
        def radios():
            try:
                return self.parent.radios()
            except Exception as e:
                raise HTTPException(400, str(e)) from e

        @self.router.get("/fs")
        def list_dir(path: str | None = None):
            try:
                return self.parent.list_dir(path)
            except ValueError as e:
                raise HTTPException(400, str(e)) from e
