"""The web view's binary frames, and which client gets which variant"""
import asyncio
import json
import logging

import numpy as np
import pytest

pytest.importorskip("fastapi")

from pyspecan.controller.WEB.websocket import WebSocketManager
from pyspecan.controller.WEB.wire import Decoder, Encoder, decode, quantize
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
    traces = _header(full)["data"]["plots"]["p1"]["axes"][0]["traces"]
    assert traces[0]["x"]["$"][0] == traces[1]["x"]["$"][0] # one offset: the same bytes in the message

def _header(msg: bytes) -> dict:
    import struct
    import zlib
    m = zlib.decompress(msg[4:])
    return json.loads(m[4:4 + struct.unpack_from("<I", m)[0]])

def test_lean_keeps_or_sends_the_change():
    enc, dec = Encoder(), Decoder()
    y = np.linspace(-90, -40, 1001)
    dec.decode(enc.encode(frames(y), {})[0])
    y2 = y.copy()
    y2[500] += 3 # a hold that rose in one bin
    full, lean = enc.encode(frames(y2), {})
    assert lean is not None and len(lean) < len(full) / 4
    traces = _header(lean)["data"]["plots"]["p1"]["axes"][0]["traces"]
    assert traces[0]["x"] == {"$k": 1} and traces[0]["y"]["$"][2] == "d2" and traces[0]["k"] == "p1/0/max"
    got = dec.decode(lean)["data"]["plots"]["p1"]["axes"][0]["traces"]
    np.testing.assert_allclose(got[0]["y"], y2, atol=0.005)
    np.testing.assert_array_equal(got[0]["x"], X)
    _, lean = enc.encode(frames(y2), {}) # nothing changed: every array is "the one you have"
    assert all(t[f] == {"$k": 1} for t in _header(lean)["data"]["plots"]["p1"]["axes"][0]["traces"][:2] for f in ("x", "y"))
    _, lean = enc.encode(frames(y2 + 1, X + 1), {}) # retuned and every level moved: those go whole
    traces = _header(lean)["data"]["plots"]["p1"]["axes"][0]["traces"]
    assert [(t["x"]["$"][2], t["y"]["$"][2]) for t in traces] == [("f8", "q2"), ("f8", "q2")]

def test_a_client_rebuilds_every_frame_whichever_variant_it_gets():
    """Holds, noise, values off the fine grid, NaN, traces coming and going: a client that takes lean after a frame it
    got and full after one it missed always sees what full alone decodes to"""
    rng = np.random.default_rng(1)
    enc, dec = Encoder(), Decoder()
    hold = np.full(300, -120.0)
    got_previous = False
    for i in range(200):
        hold = np.maximum(hold, rng.normal(-80, 10, 300)) if i % 50 else np.full(300, -120.0)
        noise = rng.normal(-80, 10, 300)
        big = noise * (1e3 if i % 7 == 0 else 1) # past ±327: a coarser grid that frame
        odd = noise.copy()
        odd[rng.integers(0, 300, 3)] = np.nan
        traces = [Trace(hold, name="hold"), Trace(big, name="big"), Trace(odd, np.arange(300.0) * (1 + i // 40), name="odd")]
        if i % 3:
            traces.append(Trace(noise[:i % 50 + 1], name="sometimes"))
        full, lean = enc.encode({"p": Frame([Axis(traces=traces)])}, {})
        if rng.random() < 0.2: # skipped by flow control
            got_previous = False
            continue
        msg = lean if lean is not None and got_previous else full
        got_previous = True
        want = Decoder().decode(full)["data"]["plots"]["p"]["axes"][0]["traces"]
        have = dec.decode(msg)["data"]["plots"]["p"]["axes"][0]["traces"]
        for w, h in zip(want, have):
            for f in ("x", "y"):
                if f in w:
                    np.testing.assert_array_equal(w[f], h[f])
        np.testing.assert_allclose(have[0]["y"], hold, atol=0.005)

def test_quantize_grid():
    q, mid, step = quantize([-150.0, 20.0])
    assert (mid, step) == (0.0, 0.01) # a fixed grid: frames compare
    q, mid, step = quantize(np.array([-1e5, 2e5]))
    assert step >= 2e5 * 1.5 / 65534 and np.log2(step / 0.01) == int(np.log2(step / 0.01))
    np.testing.assert_allclose(mid + q * step, [-1e5, 2e5], atol=step / 2)
    q, mid, step = quantize(np.full(5, 72120.1)) # constant, beyond the fine grid: a marker trend's frequency
    np.testing.assert_allclose(mid + q * step, 72120.1, atol=step / 2)

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

def test_state_leaves_out_what_never_changes_after_the_first():
    from pyspecan.controller.WEB.base import Controller
    class Fake:
        STATIC_STATE = Controller.STATIC_STATE
        state_message = Controller.state_message
        def get_state(self):
            return {"playing": True, "plot_types": ["PSD"], "plot_info": {"PSD": {}}, "categories": ["Spectrum"],
                    "colormaps": {"magma": []}, "plot_fields": {"PSD": [{"key": "vbw"}]},
                    "plots": {"p1": {"name": "PSD", "fields": [{"key": "vbw"}], "settings": {"vbw": 3}}}}
    full = decode(Fake().state_message(full=True))["data"]
    lean = decode(Fake().state_message(full=False))["data"]
    assert full == Fake().get_state()
    assert lean == {"playing": True, "plots": {"p1": {"name": "PSD", "settings": {"vbw": 3}}}}
