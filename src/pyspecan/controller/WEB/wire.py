"""Binary frame messages for the browser

A message is `[u32 header length][header, json utf-8][padding to 8][blobs]`. The header is the message with its
arrays replaced by `{"$": [offset, length, type, ...]}`, offset in bytes from the start of the blob area (8-aligned
so the browser views them in place as typed arrays). Types, all little endian:

- "f8" float64: a trace's x. Frequencies in Hz need more digits than float32 has (2.4 GHz with 1 kHz bins).
- "u1" uint8: image and surface data.
- "q2" `[offset, length, "q2", mid, step]`: a trace's y / z as int16 steps from mid, -32768 marking a value that is
  not finite. Within ±327.67 the grid is 0.01 around 0 (the 2 decimals the json form had), wider values get a coarser
  power-of-2 step. A fixed grid keeps one frame's values comparable to the next's.
- "d2" `[offset, length, "d2"]`: what changed since the previous frame's values of the same array, int16 differences
  (wrapping) on the same grid. Holds change in a few bins a frame, so this is mostly zeros.

q2 and d2 blobs are byte shuffled, all low bytes then all high bytes: the high bytes of nearby levels are alike, and
grouped they compress.

Every trace carries a key "k" (plot / axis / name). An array that did not change at all since the previous frame
is `{"$k": 1}`, "the one you have". d2 and $k only make sense to a client that got the previous frame, so a frame
comes in two variants: `lean` with them, `full` without (the websocket manager picks per client, see
WebSocketManager). Identical blobs in one message (traces sharing their x) are stored once.

Messages go deflated, compressed once here instead of once per client by the websocket's permessage-deflate (which
the server turns off): `[u32 0xffffffff][zlib stream of the message above]`. A header is never that long.
"""
import json
import math
import struct
import zlib

import numpy as np

from ...plots.frame import Frame, Image, Surface, Trace

_TYPES = {"f8": "<f8", "f4": "<f4", "u1": "u1", "q2": "<i2", "d2": "<i2"}
Q_STEP = 0.01    # q2's finest step
Q_NAN = -32768   # q2's "not finite"
Q_MAX = 32767
DELTA_MAX = 0.5  # a d2 is sent while fewer than this share of the values changed, else the q2 is smaller
DEFLATED = 0xFFFFFFFF
LEVEL = 6        # zlib level: 1 is barely faster on these sizes and compresses less

def _pad8(n: int) -> int:
    return (n + 7) & ~7

def shuffle(q: np.ndarray) -> bytes:
    """int16 -> all low bytes, then all high bytes"""
    return np.ascontiguousarray(q, dtype="<i2").view(np.uint8).reshape(-1, 2).T.tobytes()

def unshuffle(b: bytes, n: int) -> np.ndarray:
    return np.frombuffer(b, dtype=np.uint8, count=2 * n).reshape(2, n).T.copy().view("<i2").ravel()

def quantize(a) -> tuple[np.ndarray, float, float]:
    """(q, mid, step): int16 steps from mid. 0.01 around 0 within ±327.67, wider values a coarser power-of-2 step
    (and a mid on a coarse grid), so frame after frame mostly lands on the same grid"""
    a = np.asarray(a, dtype=np.float64).ravel()
    ok = np.isfinite(a)
    lo, hi = (float(a[ok].min()), float(a[ok].max())) if ok.any() else (0.0, 0.0)
    if -Q_MAX * Q_STEP <= lo and hi <= Q_MAX * Q_STEP:
        mid, step = 0.0, Q_STEP
    else:
        span = max(hi - lo, Q_STEP) # a constant (a marker's frequency block after block) still needs a step
        step = Q_STEP * 2.0 ** max(0, math.ceil(math.log2(span / 60000 / Q_STEP)))
        grain = step * 2048 # 60000 steps cover the span, the margin takes mid's rounding
        mid = round((lo + hi) / 2 / grain) * grain
    q = np.full(a.size, Q_NAN, dtype="<i2")
    q[ok] = np.clip(np.rint((a[ok] - mid) / step), -Q_MAX, Q_MAX)
    return q, mid, step

class _Blobs:
    """The blob area of one message, identical blobs stored once"""
    def __init__(self):
        self.parts: list[bytes] = []
        self.size = 0
        self.seen: dict[bytes, int] = {}

    def store(self, b: bytes) -> int:
        off = self.seen.get(b)
        if off is None:
            off = self.seen[b] = self.size
            self.parts.append(b)
            pad = _pad8(len(b)) - len(b)
            if pad:
                self.parts.append(b"\0" * pad)
            self.size += len(b) + pad
        return off

    def ref(self, spec) -> dict:
        """A header entry for an array spec: ("keep",) or (bytes, length, type, *extra)"""
        if spec[0] == "keep":
            return {"$k": 1}
        b, n, kind, *extra = spec
        return {"$": [self.store(b), n, kind, *extra]}

def pack(header: dict, blobs: _Blobs | None = None) -> bytes:
    head = json.dumps(header, separators=(",", ":")).encode()
    pad = _pad8(4 + len(head)) - 4 - len(head)
    return b"".join([struct.pack("<I", len(head)), head, b" " * pad, *(blobs.parts if blobs else ())]) # spaces: valid json

def deflate(msg: bytes) -> bytes:
    return struct.pack("<I", DEFLATED) + zlib.compress(msg, LEVEL)

def encode_json(message: dict) -> bytes:
    """A message without arrays (the state), deflated"""
    return deflate(pack(message))

def _trace(t: Trace) -> dict:
    d = {"y": t.y, "color": t.color, "kind": t.kind, "alpha": t.alpha, "width": t.width, "name": t.name}
    if t.x is not None:
        d["x"] = t.x
    if t.z is not None:
        d["z"] = t.z
    return d

def _axis(ax) -> dict:
    d = {k: getattr(ax, k) for k in (
        "xmin", "xmax", "ymin", "ymax", "zmin", "zmax", "xfmt", "yfmt", "xlabel", "ylabel", "xlog",
        "square", "projection", "aspect", "offscale")}
    for k in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax"):
        if d[k] is not None:
            d[k] = float(d[k])
    d["traces"] = [_trace(t) for t in ax.traces]
    d["markers"] = [{"x": float(m.x), "y": float(m.y), "label": m.label, "color": m.color, "kind": m.kind, "owner": m.owner,
                     "edit": m.edit} for m in ax.markers]
    d["bands"] = [{"lo": float(b.lo), "hi": float(b.hi), "ylo": None if b.ylo is None else float(b.ylo),
                   "yhi": None if b.yhi is None else float(b.yhi), "color": b.color, "alpha": b.alpha,
                   "label": b.label, "owner": b.owner, "edit": list(b.edit) if b.edit else None} for b in ax.bands]
    if ax.surface is not None:
        sf: Surface = ax.surface
        data = np.asarray(sf.data, dtype=np.uint8)
        d["surface"] = {"data": data, "rows": data.shape[0], "cols": data.shape[1], "cmap": sf.cmap}
    if ax.image is not None:
        im: Image = ax.image
        data = np.asarray(im.data, dtype=np.uint8)
        d["image"] = {"data": data, "rows_in": data.shape[0], "cols": data.shape[1], "cmap": im.cmap,
                      "scroll": im.scroll, "rows": im.rows, "clear": im.clear}
    return d

def _frame(f: Frame) -> dict:
    return {"title": f.title, "ptime": f.ptime, "readout": [[str(k), str(v)] for k, v in f.readout],
            "table": None if f.table is None else {
                "columns": list(f.table.columns), "rows": [{"id": r.id, "cells": [str(c) for c in r.cells]} for r in f.table.rows]},
            "axes": [_axis(ax) for ax in f.axes]}

class Encoder:
    """Turns the frames of one tick into messages, remembers the trace arrays of the previous tick"""
    def __init__(self):
        self.prev: dict[tuple[str, str], tuple] = {} # (trace key, field) -> x bytes, or (q, mid, step)

    def _specs(self, key: str, field: str, value, cur: dict, may_lean: bool) -> tuple[tuple, tuple]:
        """(plain, lean) specs of one trace array, and remembers it in `cur`"""
        prev = self.prev.get((key, field)) if may_lean else None
        if field == "x":
            a = np.ascontiguousarray(value, dtype="<f8").ravel()
            b = a.tobytes()
            cur[(key, field)] = b
            plain = (b, a.size, "f8")
            return plain, (("keep",) if prev == b else plain)
        q, mid, step = quantize(value)
        cur[(key, field)] = (q, mid, step)
        plain = (shuffle(q), q.size, "q2", mid, step)
        if prev is None or prev[1:] != (mid, step) or len(prev[0]) != q.size:
            return plain, plain
        d = q - prev[0] # int16: wraps, and wraps back on the client
        changed = np.count_nonzero(d)
        if changed == 0:
            return plain, ("keep",)
        if changed < DELTA_MAX * q.size:
            return plain, (shuffle(d), q.size, "d2")
        return plain, plain

    def encode(self, frames: dict[str, Frame], status: dict) -> tuple[bytes, bytes | None]:
        """(full, lean): full carries every array, lean leaves out or sends the difference of the ones a client
        that got the previous frame has. lean is None when it would be the same as full"""
        plots = {pid: _frame(frame) for pid, frame in frames.items()}
        keys = [f"{pid}/{ai}/{t['name']}" for pid, fd in plots.items() for ai, ax in enumerate(fd["axes"]) for t in ax["traces"]]
        dup = {k for k in keys if keys.count(k) > 1} # two traces under one key (same name on one axis): never lean
        cur: dict = {}
        lean_differs = False
        for pid, fd in plots.items():
            for ai, ax in enumerate(fd["axes"]):
                for t in ax["traces"]:
                    key = t["k"] = f"{pid}/{ai}/{t['name']}"
                    for field in ("x", "y", "z"):
                        if field in t:
                            plain, lean = self._specs(key, field, t[field], cur, key not in dup)
                            t[field] = (plain, lean)
                            lean_differs |= lean is not plain
        self.prev = cur

        def build(lean: bool) -> bytes:
            blobs = _Blobs()
            out = {}
            for pid, fd in plots.items():
                axes = []
                for ax in fd["axes"]:
                    a = dict(ax)
                    a["traces"] = []
                    for t in ax["traces"]:
                        td = dict(t)
                        for field in ("x", "y", "z"):
                            if field in t:
                                td[field] = blobs.ref(t[field][1 if lean else 0])
                        a["traces"].append(td)
                    for k in ("surface", "image"):
                        if k in ax:
                            data = ax[k]["data"]
                            a[k] = dict(ax[k], data=blobs.ref((data.tobytes(), data.size, "u1")))
                    axes.append(a)
                out[pid] = dict(fd, axes=axes)
            return pack({"type": "frame", "data": {"plots": out, "status": status}}, blobs)

        full = deflate(build(False))
        return full, (deflate(build(True)) if lean_differs else None)

class Decoder:
    """What the browser does with the messages, for tests: keeps the trace arrays to resolve $k and d2 against"""
    def __init__(self):
        self.cache: dict[tuple[str, str], tuple] = {} # (key, field) -> (value, q or None)

    def decode(self, msg: bytes) -> dict:
        (hlen,) = struct.unpack_from("<I", msg)
        if hlen == DEFLATED:
            msg = zlib.decompress(msg[4:])
            (hlen,) = struct.unpack_from("<I", msg)
        base = _pad8(4 + hlen)
        def hook(d):
            if "$" in d and len(d) == 1:
                off, n, kind, *extra = d["$"]
                if kind in ("q2", "d2"):
                    return {kind: unshuffle(msg[base + off:base + off + 2 * n], n), "extra": extra}
                return np.frombuffer(msg, dtype=_TYPES[kind], count=n, offset=base + off)
            return d
        out = json.loads(msg[4:4 + hlen], object_hook=hook)
        for frame in (out.get("data", {}).get("plots") or {}).values() if out.get("type") == "frame" else ():
            for ax in frame["axes"]:
                for t in ax["traces"]:
                    for field in ("x", "y", "z"):
                        if field in t:
                            t[field] = self._resolve((t["k"], field), t[field])
        return out

    def _resolve(self, ck, v):
        if isinstance(v, dict) and v.get("$k"):
            return self.cache[ck][0]
        if isinstance(v, dict) and "q2" in v:
            q, (mid, step) = v["q2"], v["extra"]
        elif isinstance(v, dict) and "d2" in v:
            _, q0, mid, step = self.cache[ck]
            q = (q0 + v["d2"]).astype("<i2") # wraps as the encoder's subtraction did
        else:
            self.cache[ck] = (v, None, None, None)
            return v
        val = np.where(q == Q_NAN, np.nan, mid + q.astype(np.float64) * step)
        self.cache[ck] = (val, q, mid, step)
        return val

def decode(msg: bytes) -> dict:
    """One message on its own (a full frame, a state), for tests"""
    return Decoder().decode(msg)
