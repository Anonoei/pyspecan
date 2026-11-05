"""WEB base plots: compute plot data, the browser only draws it

A frame is a json-serializable dict: {"axes": [axis, ...]}, where an axis is
    {"xmin", "xmax", "xfmt": "freq"|"num", "ymin", "ymax",   (None -> browser autoranges)
     "square": bool,
     "series": [{"x"?, "y", "color", "kind": "line"|"scatter"}],
     "image": {"row": base64 uint8, "rows": int, "clear": bool}}   (instead of series)
"""
import numpy as np

from ....utils.psd import psd
from ....utils.window import WindowLUT

def rounded(arr, digits=2):
    return np.round(arr, digits).tolist()

class _Plot:
    """base plot"""
    TITLE = ""
    FIELDS: list[dict] = [] # settings the browser can edit: key, label, kind (number|text|select|check)

    def __init__(self, parent, **kwargs):
        self.parent = parent
        self.enabled = True # False -> paused

    @property
    def model(self):
        return self.parent.model

    def update(self, samps):
        """Process samples, returns a frame (or None if paused)"""
        if not self.enabled:
            return None
        return self._update(samps)

    def reset(self):
        """Reset accumulated plot state"""

    def settings(self) -> dict:
        return {"enabled": self.enabled, **{f["key"]: getattr(self, f["key"]) for f in self.FIELDS}}

    def fields(self) -> list[dict]:
        return self.FIELDS

    def set(self, key, value):
        if key == "enabled":
            self.enabled = bool(value)
        elif any(f["key"] == key for f in self.fields()):
            getattr(self, f"set_{key}")(value)
        else:
            raise ValueError(f"unknown plot setting {key!r}")

    def _update(self, samps):
        raise NotImplementedError()

    def _freq_range(self):
        fs, cf = self.model.get_fs().raw, self.model.get_cf().raw
        return cf - fs/2, cf + fs/2

class FreqPlot(_Plot):
    FIELDS = [
        {"key": "ref_level", "label": "Ref level", "kind": "text", "hint": "auto"},
        {"key": "scale_div", "label": "Scale / div", "kind": "number", "min": 0.1, "step": 1},
        {"key": "vbw", "label": "VBW", "kind": "number", "min": 0, "step": 1},
        {"key": "window", "label": "Window", "kind": "select", "options": list(WindowLUT.keys())},
    ]
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.window = kwargs.get("window", "blackman")
        self.vbw = kwargs.get("vbw", 10.0)
        self.scale_div = kwargs.get("scale_div", 10.0)
        self.ref_level = kwargs.get("ref_level", "auto")
        self._auto = None # resolved level while ref_level is "auto"

    def calc_psd(self, samps):
        vbw = self.vbw if self.vbw > 0 else None
        return psd(samps, self.model.get_fs().raw, vbw, self.window)

    def resolve_ref(self, _psd):
        """Return the numeric ref level, resolving "auto" from the first psd"""
        if self.ref_level != "auto":
            return self.ref_level
        if self._auto is None:
            pmax = np.max(_psd)
            self._auto = int(pmax * 0.9) if pmax < 0 else int(pmax * 1.1)
        return self._auto

    def y_range(self, _psd):
        top = self.resolve_ref(_psd)
        return top - 10*self.scale_div, top

    def set_scale_div(self, scale):
        scale = float(scale)
        if scale <= 0:
            raise ValueError("scale must be positive")
        self.scale_div = scale

    def set_ref_level(self, ref):
        self._auto = None
        self.ref_level = "auto" if str(ref).strip().lower() in ("", "auto") else float(ref)

    def set_vbw(self, vbw):
        self.vbw = max(float(vbw), 0.0)
        self.reset()

    def set_window(self, window):
        if window not in WindowLUT:
            raise ValueError(f"unknown window {window!r}")
        self.window = window
        self.reset()
