"""WebSocket client management"""
import asyncio
import itertools
import json
import time

from fastapi import WebSocket

MAX_IN_FLIGHT = 2 # frames sent to a client that it has not acknowledged yet
STALL = 2.0        # [s] without an ack and the client is treated as not acknowledging at all

class WebSocketManager:
    """Connected clients. Frames are flow controlled: the browser acknowledges every frame it has
    drawn, and a client that is still busy with earlier ones is skipped instead of queued behind.
    Without that, a slow client (big images) lags further and further behind, and everything else
    sent to it (a layout change, an error) waits behind the backlog.

    Messages are encoded once, on the publishing thread, and the same bytes go to every client. A frame
    comes in two variants (see `wire`): `lean` leaves out the x arrays that did not change since the previous
    frame, so only a client that got the previous frame may have it, the others get `full`.
    A client whose page is hidden (a background tab) gets no frames at all."""
    def __init__(self, parent):
        self.parent = parent
        self.log = parent.log
        self.connections: dict[int, WebSocket] = {}
        self.in_flight: dict[int, int] = {}
        self.last_ack: dict[int, float] = {}
        self.last_seq: dict[int, int] = {}   # the last frame sent to the client
        self.visible: dict[int, bool] = {}
        self.loop: asyncio.AbstractEventLoop | None = None
        self._ids = itertools.count()
        self._seq = itertools.count(1)
        self._order: asyncio.Lock | None = None # one broadcast at a time: frames reach each client in order

    async def connect(self, websocket: WebSocket) -> int:
        await websocket.accept()
        self.loop = asyncio.get_running_loop()
        client_id = next(self._ids)
        self.connections[client_id] = websocket
        self.in_flight[client_id] = 0
        self.last_ack[client_id] = time.monotonic()
        self.last_seq[client_id] = -1
        self.visible[client_id] = True
        self.log.info("client %s connected", client_id)
        return client_id

    def disconnect(self, client_id: int):
        for d in (self.in_flight, self.last_ack, self.last_seq, self.visible):
            d.pop(client_id, None)
        if self.connections.pop(client_id, None) is not None:
            self.log.info("client %s disconnected", client_id)

    def ack(self, client_id: int):
        """The client drew a frame"""
        if client_id in self.in_flight:
            self.in_flight[client_id] = max(0, self.in_flight[client_id] - 1)
            self.last_ack[client_id] = time.monotonic()

    def set_visible(self, client_id: int, visible: bool):
        if client_id in self.visible:
            self.visible[client_id] = bool(visible)
            if visible: # back from the background: whatever it had in flight was never drawn
                self.in_flight[client_id] = 0
                self.last_ack[client_id] = time.monotonic()

    def watching(self) -> bool:
        """Some client shows frames"""
        return any(self.visible.values())

    async def send(self, client_id: int, message: dict | bytes) -> bool:
        """Send to one client, False when it is gone (closed mid-send, or dropped by a broadcast already)"""
        websocket = self.connections.get(client_id)
        if websocket is None:
            return False
        try:
            if isinstance(message, bytes):
                await websocket.send_bytes(message)
            else:
                await websocket.send_json(message)
        except Exception: # client went away mid-send, like in broadcast
            self.disconnect(client_id)
            return False
        return True

    async def _send_raw(self, client_id: int, websocket: WebSocket, data: str | bytes) -> bool:
        try:
            if isinstance(data, bytes):
                await websocket.send_bytes(data)
            else:
                await websocket.send_text(data)
        except Exception: # client went away mid-send
            self.disconnect(client_id)
            return False
        return True

    async def broadcast(self, data: str | bytes, frame=False, seq=0, lean: bytes | None = None):
        if self._order is None:
            self._order = asyncio.Lock()
        async with self._order:
            for client_id, websocket in list(self.connections.items()):
                if frame:
                    if not self.visible.get(client_id, True):
                        continue
                    if self.in_flight.get(client_id, 0) >= MAX_IN_FLIGHT:
                        if time.monotonic() - self.last_ack.get(client_id, 0) < STALL:
                            continue # still busy, this frame is skipped
                        self.in_flight[client_id] = 0 # it stopped acknowledging, don't starve it
                    self.in_flight[client_id] = self.in_flight.get(client_id, 0) + 1
                    out = lean if lean is not None and self.last_seq.get(client_id) == seq - 1 else data
                    self.last_seq[client_id] = seq
                else:
                    out = data
                await self._send_raw(client_id, websocket, out)

    def publish(self, message: dict | str | bytes, frame=False, lean: bytes | None = None):
        """Thread-safe broadcast, for use outside the event loop. The message is encoded here, once.
        `frame` messages are flow controlled, `lean` is the variant for clients that got the previous frame"""
        seq = next(self._seq) if frame else 0 # counts every published frame, also ones nobody gets
        if self.loop is None or not self.connections:
            return
        data = json.dumps(message, separators=(",", ":")) if isinstance(message, dict) else message
        asyncio.run_coroutine_threadsafe(self.broadcast(data, frame, seq, lean), self.loop)
