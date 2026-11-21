"""Binary frame messages for the browser

A frame message is `[u32 header length][header, json utf-8][padding to 8][blobs]`. The header is the
`frame` message with its arrays replaced by `{"$": [offset, length, type]}`, offset in bytes from the start
of the blob area (8-aligned so the browser views them in place as typed arrays). Types: "f8" float64,
"f4" float32, "u1" uint8, all little endian.

Trace y / z go as "q2": int16 steps of 0.01 (or coarser, when the values span more than ±327) from an offset, the header
ref is `[offset, length, "q2", start, step]` and -32768 marks a value that is not finite. That is the precision the json
form had (it kept 2 decimals), in half the bytes of float32, and it compresses. x stays float64: frequencies in Hz need more digits
than float32 has (2.4 GHz with 1 kHz bins).

A trace's x seldom changes (the same frequency grid every frame), so it is only sent when it differs from the
previous frame's: otherwise the header holds `{"$k": 1}`, "the x you have". That is only valid for a client that
received the previous frame; one that skipped it (flow control) gets the `full` variant instead. Identical blobs in
one message (the holds and the trace share their x) are stored once.

Frames go deflated, compressed once here instead of once per client by the websocket's permessage-deflate (which
the server turns off): `[u32 0xffffffff][zlib stream of the message above]`. A header is never that long.
"""
import json
import struct
import zlib

import numpy as np

from ...plots.frame import Frame, Image, Surface, Trace

_TYPES = {"f8": "<f8", "f4": "<f4", "u1": "u1", "q2": "<i2"}
Q_STEP = 0.01   # q2's finest step
Q_NAN = -32768  # q2's "not finite"
DEFLATED = 0xFFFFFFFF
LEVEL = 6       # zlib level: 1 is barely faster on these sizes and compresses less

def _pad8(n: int) -> int:
    return (n + 7) & ~7

class _Blobs:
    """The blob area of one message, identical blobs stored once"""
    def __init__(self):
        self.parts: list[bytes] = []
        self.size = 0
        self.seen: dict[bytes, int] = {}

    def add(self, arr, kind: str) -> dict:
        if kind == "q2":
            return self._q2(np.asarray(arr, dtype=np.float64).ravel())
        a = np.ascontiguousarray(arr, dtype=_TYPES[kind]).ravel()
        return {"$": [self._store(a.tobytes()), int(a.size), kind]}

    def _q2(self, a: np.ndarray) -> dict:
        ok = np.isfinite(a)
        lo, hi = (float(a[ok].min()), float(a[ok].max())) if ok.any() else (0.0, 0.0)
        step = max(Q_STEP, (hi - lo) / 65534)
        mid = round((lo + hi) / 2 / step) * step # on the step grid: values land where the json's rounding put them
        q = np.full(a.size, Q_NAN, dtype="<i2")
        q[ok] = np.clip(np.rint((a[ok] - mid) / step), -32767, 32767)
        return {"$": [self._store(q.tobytes()), int(a.size), "q2", mid, step]}

    def _store(self, b: bytes) -> int:
        off = self.seen.get(b)
        if off is None:
            off = self.seen[b] = self.size
            self.parts.append(b)
            pad = _pad8(len(b)) - len(b)
            if pad:
                self.parts.append(b"\0" * pad)
            self.size += len(b) + pad
        return off

def _pack(header: dict, blobs: _Blobs) -> bytes:
    head = json.dumps(header, separators=(",", ":")).encode()
    pad = _pad8(4 + len(head)) - 4 - len(head)
    return b"".join([struct.pack("<I", len(head)), head, b" " * pad, *blobs.parts]) # spaces: still valid json

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
    """Turns the frames of one tick into messages, remembers the x arrays of the previous tick"""
    def __init__(self):
        self.prev_x: dict[str, bytes] = {}

    def reset(self):
        self.prev_x = {}

    def encode(self, frames: dict[str, Frame], status: dict) -> tuple[bytes, bytes | None]:
        """(full, lean): full carries every x, lean only those that changed since the previous call (None when
        that is all of them, then full is all there is)"""
        plots = {pid: _frame(frame) for pid, frame in frames.items()}
        cur: dict[str, bytes] = {}
        dup = set() # two traces under one key (same name on one axis): never "the x you have"
        for pid, fd in plots.items():
            for ai, ax in enumerate(fd["axes"]):
                for t in ax["traces"]:
                    if "x" in t:
                        key = f"{pid}/{ai}/{t['name']}"
                        t["x"] = np.ascontiguousarray(t["x"], dtype="<f8").ravel()
                        if key in cur:
                            dup.add(key)
                        cur[key] = t["x"].tobytes()
        same = {k for k, b in cur.items() if k not in dup and self.prev_x.get(k) == b}
        self.prev_x = cur

        def build(lean: bool) -> bytes:
            blobs = _Blobs()
            out = {}
            for pid, fd in plots.items():
                axes = []
                for ai, ax in enumerate(fd["axes"]):
                    a = dict(ax)
                    a["traces"] = []
                    for t in ax["traces"]:
                        td = dict(t)
                        td["y"] = blobs.add(t["y"], "q2")
                        if "z" in t:
                            td["z"] = blobs.add(t["z"], "q2")
                        if "x" in t:
                            key = f"{pid}/{ai}/{t['name']}"
                            td["xk"] = key
                            td["x"] = {"$k": 1} if lean and key in same else blobs.add(t["x"], "f8")
                        a["traces"].append(td)
                    for k in ("surface", "image"):
                        if k in ax:
                            a[k] = dict(ax[k], data=blobs.add(ax[k]["data"], "u1"))
                    axes.append(a)
                out[pid] = dict(fd, axes=axes)
            return _pack({"type": "frame", "data": {"plots": out, "status": status}}, blobs)

        full = deflate(build(False))
        return full, (deflate(build(True)) if same else None)

def deflate(msg: bytes) -> bytes:
    return struct.pack("<I", DEFLATED) + zlib.compress(msg, LEVEL)

def decode(msg: bytes) -> dict:
    """The message back as a dict of numpy arrays (`{"$k": 1}` stays as it is), for tests"""
    (hlen,) = struct.unpack_from("<I", msg)
    if hlen == DEFLATED:
        msg = zlib.decompress(msg[4:])
        (hlen,) = struct.unpack_from("<I", msg)
    base = _pad8(4 + hlen)
    def hook(d):
        if "$" in d and len(d) == 1:
            off, n, kind = d["$"][:3]
            a = np.frombuffer(msg, dtype=_TYPES[kind], count=n, offset=base + off)
            if kind == "q2":
                mid, step = d["$"][3:]
                return np.where(a == Q_NAN, np.nan, mid + a.astype(np.float64) * step)
            return a
        return d
    return json.loads(msg[4:4 + hlen], object_hook=hook)
