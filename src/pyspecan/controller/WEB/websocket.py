"""WebSocket client management"""
import asyncio
import itertools

from fastapi import WebSocket

class WebSocketManager:
    def __init__(self, parent):
        self.parent = parent
        self.log = parent.log
        self.connections: dict[int, WebSocket] = {}
        self.loop: asyncio.AbstractEventLoop | None = None
        self._ids = itertools.count()

    async def connect(self, websocket: WebSocket) -> int:
        await websocket.accept()
        self.loop = asyncio.get_running_loop()
        client_id = next(self._ids)
        self.connections[client_id] = websocket
        self.log.info("client %s connected", client_id)
        return client_id

    def disconnect(self, client_id: int):
        if self.connections.pop(client_id, None) is not None:
            self.log.info("client %s disconnected", client_id)

    async def send(self, client_id: int, message: dict):
        await self.connections[client_id].send_json(message)

    async def broadcast(self, message: dict):
        for client_id, websocket in list(self.connections.items()):
            try:
                await websocket.send_json(message)
            except Exception: # client went away mid-send
                self.disconnect(client_id)

    def publish(self, message: dict):
        """Thread-safe broadcast, for use outside the event loop"""
        if self.loop is None or not self.connections:
            return
        asyncio.run_coroutine_threadsafe(self.broadcast(message), self.loop)
