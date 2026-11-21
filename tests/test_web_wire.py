"""The web view's binary frames, and which client gets which variant"""
import asyncio
import json
import logging

import numpy as np
import pytest

pytest.importorskip("fastapi")

from pyspecan.controller.WEB.websocket import WebSocketManager
from pyspecan.controller.WEB.wire import Encoder, decode
from pyspecan.plots.frame import Axis, Band, Frame, Image, Marker, Surface, Table, TableRow, Trace

X = np.linspace(2.4e9, 2.41e9, 1001) # needs float64: float32 can not tell 1 kHz apart at 2.4 GHz

def frames(y, x=X):
    return {"p1": Frame([
        Axis(xmin=2.4e9, xmax=2.41e9, traces=[Trace(y, x, name="max"), Trace(y - 1, x, name="psd")],
             markers=[Marker(2.405e9, -50.0, "M1")], bands=[Band(2.401e9, 2.402e9)]),
        Axis(image=Image(np.arange(12, dtype=np.uint8).reshape(3, 4), scroll=True, rows=10),
             traces=[Trace(np.array([np.nan, np.inf, 1.234]), name="odd")]),
        Axis(projection="3d", surface=Surface(np.full((2, 3), 7, dtype=np.uint8))),
    ], title="PSD", readout=[("RBW", "1 kHz")], table=Table(["a"], [TableRow("m1", ["1"])]))}

def test_round_trip_matches_the_json_form():
    rng = np.random.default_rng(0)
    y = rng.standard_normal(1001) * 20 - 80
    fs = frames(y)
    full, lean = Encoder().encode(fs, {"seq": 3})
    assert lean is None # the first frame: every x is new
    msg = decode(full)
    ref = json.loads(json.dumps(fs["p1"].to_dict(digits=6)))
    got = msg["data"]["plots"]["p1"]
    assert msg["type"] == "frame" and msg["data"]["status"] == {"seq": 3}
    assert got["title"] == ref["title"] and got["readout"] == ref["readout"] and got["table"] == ref["table"]
    a0 = got["axes"][0]
    assert a0["markers"] == ref["axes"][0]["markers"] and a0["bands"] == ref["axes"][0]["bands"]
    np.testing.assert_array_equal(a0["traces"][0]["x"], X) # exact
    np.testing.assert_allclose(a0["traces"][1]["y"], y - 1, atol=0.005) # the json form's 2 decimals
    odd = got["axes"][1]["traces"][0]["y"]
    assert np.isnan(odd[:2]).all() and abs(odd[2] - 1.234) <= 0.005 # not finite survives (json would break on it)
    im = got["axes"][1]["image"]
    assert list(im["data"]) == list(range(12)) and (im["rows_in"], im["cols"], im["rows"], im["scroll"]) == (3, 4, 10, True)
    assert list(got["axes"][2]["surface"]["data"]) == [7] * 6

def test_shared_x_is_stored_once():
    full, _ = Encoder().encode(frames(np.zeros(1001)), {})
    ref = decode(full)["data"]["plots"]["p1"]["axes"][0]["traces"]
    assert ref[0]["x"].ctypes.data == ref[1]["x"].ctypes.data # the same bytes in the message

def test_lean_leaves_out_only_the_unchanged_x():
    enc = Encoder()
    enc.encode(frames(np.zeros(1001)), {})
    full, lean = enc.encode(frames(np.ones(1001)), {})
    assert lean is not None and len(lean) < len(full)
    traces = decode(lean)["data"]["plots"]["p1"]["axes"][0]["traces"]
    assert [t["x"] for t in traces] == [{"$k": 1}, {"$k": 1}] and traces[0]["xk"] == "p1/0/max"
    np.testing.assert_allclose(traces[0]["y"], 1, atol=0.005)
    _, lean = enc.encode(frames(np.ones(1001), X + 1), {}) # retuned: every x changed
    assert lean is None

def test_two_traces_under_one_key_always_carry_their_x():
    enc = Encoder()
    f = lambda: {"p": Frame([Axis(traces=[Trace(np.zeros(3), np.arange(3.0), name="t"), Trace(np.zeros(3), np.arange(3.0) + 5, name="t")])])}
    enc.encode(f(), {})
    assert enc.encode(f(), {})[1] is None

def test_deflated():
    full, _ = Encoder().encode(frames(np.zeros(1001)), {})
    assert full[:4] == b"\xff\xff\xff\xff"

class Client:
    def __init__(self):
        self.got = []
    async def accept(self): pass
    async def send_bytes(self, b): self.got.append(b)
    async def send_text(self, t): self.got.append(t)

def test_lean_only_to_clients_that_got_the_previous_frame_and_none_to_hidden_ones():
    class Parent:
        log = logging.getLogger("test")
    ws = WebSocketManager(Parent())
    a, b, c = Client(), Client(), Client()
    async def run():
        ia, ib, ic = [await ws.connect(x) for x in (a, b, c)]
        ws.set_visible(ic, False)
        assert ws.watching()
        async def frame(n, lean=None, busy=()):
            for i in busy:
                ws.in_flight[i] = 2 # still drawing: skips this one
            await ws.broadcast(f"F{n}".encode(), frame=True, seq=n, lean=lean)
            for i in (ia, ib, ic):
                ws.in_flight[i] = 0 # drawn
        await frame(1)
        await frame(2, b"L2", busy=[ib])
        await frame(3, b"L3")
        ws.set_visible(ic, True)
        await frame(4, b"L4")
        await ws.broadcast('{"type":"state"}')
        ws.set_visible(ia, False); ws.set_visible(ib, False); ws.set_visible(ic, False)
        assert not ws.watching() # playback pauses
    asyncio.run(run())
    assert a.got == [b"F1", b"L2", b"L3", b"L4", '{"type":"state"}']
    assert b.got == [b"F1", b"F3", b"L4", '{"type":"state"}'] # missed 2: frame 3 in full
    assert c.got == [b"F4", '{"type":"state"}'] # hidden for 1-3, still gets the state
