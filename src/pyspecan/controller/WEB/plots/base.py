"""WEB base plots: compute plot data, the browser only draws it"""
import numpy as np

from ....utils.psd import psd

class _Plot:
    """base plot"""
    def __init__(self, parent):
        self.parent = parent
        self.enabled = True

    def toggle(self, enabled=None):
        self.enabled = (not self.enabled) if enabled is None else bool(enabled)

    def update(self, samps, **kwargs):
        """Process samples, returns a json-serializable dict (or None if disabled)"""
        if not self.enabled:
            return None
        return self._update(samps, **kwargs)

    def reset(self):
        """Reset plot state"""

    def settings(self) -> dict:
        """Return the current settings"""
        return {"enabled": self.enabled}

    def _update(self, samps, **kwargs):
        raise NotImplementedError()

class FreqPlot(_Plot):
    def __init__(self, parent, **kwargs):
        super().__init__(parent)
        self.window = kwargs.get("window", "blackman")
        self.vbw = kwargs.get("vbw", 10.0)
        self.scale = kwargs.get("scale_div", 10.0)
        self.ref_level = kwargs.get("ref_level", "auto")

    def calc_psd(self, samps):
        vbw = self.vbw if self.vbw > 0 else None
        return psd(samps, self.parent.model.get_fs().raw, vbw, self.window)

    @property
    def y_top(self):
        """Plot maximum amplitude"""
        return self.ref_level
    @property
    def y_btm(self):
        """Plot minimum amplitude"""
        return self.ref_level - (10*self.scale)

    def set_scale(self, scale):
        scale = float(scale)
        if scale <= 0:
            raise ValueError("scale must be positive")
        self.scale = scale

    def set_ref_level(self, ref):
        self.ref_level = "auto" if ref == "auto" else float(ref)

    def set_vbw(self, vbw):
        self.vbw = max(float(vbw), 0.0)

    def set_window(self, window):
        from ....utils.window import WindowLUT
        if window not in WindowLUT:
            raise ValueError(f"unknown window {window}")
        self.window = window

    def _calc_ref_level(self, _psd, mul=0.1):
        pmax = np.max(_psd)
        return int(pmax * (1-mul)) if pmax < 0 else int(pmax * (1+mul))

    def settings(self):
        return {
            **super().settings(),
            "window": self.window, "vbw": self.vbw, "scale_div": self.scale,
            "ref_level": self.ref_level,
        }
