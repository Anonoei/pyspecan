"""Web controller: FastAPI routes (`api`), the websocket clients (`websocket`), and the binary frame messages (`wire`)

Playback pauses while no browser is connected (`can_stream`). Frames are encoded once per tick for every client;
trace arrays are sent as typed arrays, deltas against the previous tick where that is smaller (see `wire`).
"""
