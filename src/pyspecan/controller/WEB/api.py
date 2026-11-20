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

        @self.router.get("/export/{pid}")
        def export(pid: str, what: str = "csv"):
            """A plot's latest frame as a file: what=csv its traces, table its marker table, json all of it"""
            try:
                with self.parent.lock:
                    text = self.parent.export(pid, what)
                    name = self.parent.plots.get(pid).NAME
            except (ValueError, KeyError) as e:
                raise HTTPException(404, str(e)) from e
            ext, media = ("json", "application/json") if what == "json" else ("csv", "text/csv")
            stem = "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")
            suffix = "-table" if what == "table" else ""
            return Response(text, media_type=media,
                            headers={"Content-Disposition": f'attachment; filename="pyspecan-{stem}{suffix}.{ext}"'})

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
