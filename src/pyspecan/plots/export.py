"""A frame as files: its traces and its table as CSV, the whole of it as JSON (images are each view's own: a PNG)"""
import csv
import io
import json

import numpy as np

from .frame import Axis, Frame, Trace


def trace_x(t: Trace, ax: Axis) -> np.ndarray:
    """A trace's x values as views draw them (see Trace): its own, one point per bin across the x range, or the index"""
    n = len(t.y)
    if t.x is not None:
        return np.asarray(t.x, dtype=np.float64)
    if ax.xmin is not None and ax.xmax is not None:
        return ax.xmin + np.arange(n) * ((ax.xmax - ax.xmin) / max(n, 1))
    return np.arange(n, dtype=np.float64)

def traces_csv(frame: Frame) -> str:
    """Every trace's points, one row each: axis (its number and y label), trace name, x, y, and z on 3d axes"""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    has_z = any(t.z is not None for ax in frame.axes for t in ax.traces)
    w.writerow(["axis", "label", "trace", "x", "y", *(["z"] if has_z else [])])
    for k, ax in enumerate(frame.axes):
        label = ax.ylabel or ax.xfmt
        for n, t in enumerate(ax.traces):
            x = trace_x(t, ax)
            y = np.asarray(t.y, dtype=np.float64)
            z = np.asarray(t.z, dtype=np.float64) if t.z is not None else None
            name = t.name or f"trace{n}"
            for i in range(len(y)):
                w.writerow([k, label, name, repr(float(x[i])), repr(float(y[i])), *([repr(float(z[i]))] if z is not None else ([""] if has_z else []))])
    return out.getvalue()

def table_csv(frame: Frame) -> str:
    """The marker / measurement table, "" without one"""
    if frame.table is None or not frame.table.rows:
        return ""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(frame.table.columns)
    for r in frame.table.rows:
        w.writerow(r.cells)
    return out.getvalue()

def frame_json(frame: Frame) -> str:
    """Everything the frame holds (as the web view receives it): axes, traces, images (base64), markers, readout, table"""
    return json.dumps(frame.to_dict(digits=6), indent=1)

FORMATS = {"csv": traces_csv, "table": table_csv, "json": frame_json} # what = function(frame) -> text
