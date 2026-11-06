"""WebSocket client management"""
import asyncio
import itertools
import time

from fastapi import WebSocket

MAX_IN_FLIGHT = 2 # frames sent to a client that it has not acknowledged yet
STALL = 2.0        # [s] without an ack and the client is treated as not acknowledging at all

class WebSocketManager:
    """Connected clients. Frames are flow controlled: the browser acknowledges every frame it has
    drawn, and a client that is still busy with earlier ones is skipped instead of queued behind.
    Without that, a slow client (big images) lags further and further behind, and everything else
    sent to it (a layout change, an error) waits behind the backlog."""
    def __init__(self, parent):
        self.parent = parent
        self.log = parent.log
        self.connections: dict[int, WebSocket] = {}
        self.in_flight: dict[int, int] = {}
        self.last_ack: dict[int, float] = {}
        self.loop: asyncio.AbstractEventLoop | None = None
        self._ids = itertools.count()

    async def connect(self, websocket: WebSocket) -> int:
        await websocket.accept()
        self.loop = asyncio.get_running_loop()
        client_id = next(self._ids)
        self.connections[client_id] = websocket
        self.in_flight[client_id] = 0
        self.last_ack[client_id] = time.monotonic()
        self.log.info("client %s connected", client_id)
        return client_id

    def disconnect(self, client_id: int):
        self.in_flight.pop(client_id, None)
        self.last_ack.pop(client_id, None)
        if self.connections.pop(client_id, None) is not None:
            self.log.info("client %s disconnected", client_id)

    def ack(self, client_id: int):
        """The client drew a frame"""
        if client_id in self.in_flight:
            self.in_flight[client_id] = max(0, self.in_flight[client_id] - 1)
            self.last_ack[client_id] = time.monotonic()

    async def send(self, client_id: int, message: dict):
        await self.connections[client_id].send_json(message)

    async def broadcast(self, message: dict, frame=False):
        for client_id, websocket in list(self.connections.items()):
            if frame:
                if self.in_flight.get(client_id, 0) >= MAX_IN_FLIGHT:
                    if time.monotonic() - self.last_ack.get(client_id, 0) < STALL:
                        continue # still busy, this frame is skipped
                    self.in_flight[client_id] = 0 # it stopped acknowledging, don't starve it
                self.in_flight[client_id] = self.in_flight.get(client_id, 0) + 1
            try:
                await websocket.send_json(message)
            except Exception: # client went away mid-send
                self.disconnect(client_id)

    def publish(self, message: dict, frame=False):
        """Thread-safe broadcast, for use outside the event loop. `frame` messages are flow controlled"""
        if self.loop is None or not self.connections:
            return
        asyncio.run_coroutine_threadsafe(self.broadcast(message, frame), self.loop)
