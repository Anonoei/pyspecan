import numpy as np

from ..utils import matrix
from .base import plot
from .freq import FreqPlot, SETTING_CMAP
from .frame import Axis, Frame, Image, Trace, IMAGE, LINE, RED, YELLOW
from .settings import Setting, override

@plot("Persistence")
class PST(FreqPlot):
    """Persistence histogram of the block's overlapped frames, the chance of a frame passing each frequency / level pixel,
    with the live trace and a max hold over it"""
    TITLE = "Persistence"
    FEATURES = frozenset({IMAGE, LINE})
    SETTINGS = override(FreqPlot.SETTINGS, vbw={"default": 0.0}) + (
        SETTING_CMAP.with_(default="hot"),
        Setting("x", "Width", "int", default=0, min=0, max=8192, flags=("--x",), help="histogram x pixels (0: one per FFT bin)"),
        Setting("y", "Height", "int", default=600, min=16, max=4096, flags=("--y",), help="histogram y pixels"),
        Setting("style", "Style", "select", default="vector", options=("vector", "dot"), reset=True, flags=("--style",),
                help="vector joins neighbouring bins, dot plots only the bins"),
        Setting("ghost", "Ghost", "number", default=0.35, min=0.0, max=1.0, step=0.05, flags=("--ghost",),
                help="how bright pixels that were lit earlier but are not now stay, 0 hides them"),
        Setting("persistence", "Ghost time (s)", "number", default=0.0, min=0.0, max=600.0, step=1, flags=("--persistence",),
                help="signal time for the ghost to fade away (0: it stays until reset)"),
        Setting("contrast", "Contrast", "number", default=1000.0, min=1.0, max=100000.0, step=100, flags=("--contrast",),
                help="how far rare hits are lifted: a pixel needs about 1/contrast of the frames to show, higher shows rarer events"),
        Setting("show_live", "Live trace", "check", default=False, flags=("--show_live",), help="the latest FFT over the histogram"),
        Setting("show_max", "Max hold", "check", default=False, flags=("--show_max",), help="max hold trace over the histogram"),
        Setting("hold_alpha", "Max hold intensity", "number", default=0.5, min=0.05, max=1.0, step=0.05, flags=("--hold_alpha",),
                help="opacity of the max hold trace, 1 can not be told from the live trace"),
    )

    def reset(self):
        super().reset()
        self._seen = None # the brightest each pixel has been, 0-1
        self._key = None
        self._max = None

    def changed(self, key):
        super().changed(key)
        if key == "show_max":
            self._max = None # restart the hold when toggled

    def _histogram(self, rows, btm, top):
        """What is lit by this block shows at full brightness and goes dark the moment it stops. Where it was lit
        earlier it shows as a dimmer ghost of the same colours"""
        width = self.x or rows.shape[-1]
        build = matrix.cvec if self.style == "vector" else matrix.dot
        mat = build(width, self.y, rows.T, top, btm).astype(np.float32)
        mat /= len(rows) # probability that a frame passes through the pixel, so block size does not matter
        # a fixed, logarithmic map of probability to colour: the colours mean the same thing every block
        # (no flicker), and a noise floor spread over many pixels is as visible as a carrier on a few
        new = np.log1p(mat * self.contrast)
        new *= 1.0 / np.log1p(self.contrast)
        np.minimum(new, 1.0, out=new)
        key = (mat.shape, btm, top)
        if key != self._key or self._seen is None: # axes moved, history no longer lines up
            self._key = key
            self._seen = new.copy()
        else:
            if self.persistence > 0:
                span = len(rows) * self.source.hop("rt", rows.shape[-1]) / self.source.fs # signal time of this block
                self._seen *= 0.05 ** (span / self.persistence)
            np.maximum(self._seen, new, out=self._seen)
        if self.ghost <= 0:
            return (new * 255.0).astype(np.uint8)
        shown = np.where(mat > 0, new, self._seen * self.ghost)
        return (shown * 255.0).astype(np.uint8)

    def _traces(self, raw):
        out = []
        if self.show_max:
            hi = raw.max(axis=0)
            if self._max is None or len(self._max) != len(hi):
                self._max = hi.copy()
            else:
                np.maximum(self._max, hi, out=self._max)
            out.append(Trace(self._max, color=RED, name="max", alpha=self.hold_alpha, width=1.0))
        if self.show_live:
            out.append(Trace(raw[-1], color=YELLOW, name="live", width=1.0))
        return out

    def render(self):
        raw = self.psd_rows("rt", smooth=False)
        if not len(raw):
            return None
        self.last = raw.mean(axis=0) # what markers measure
        rows = self.smooth(raw)
        btm, top = self.y_range(rows)
        data = self._histogram(rows, btm, top)
        fmin, fmax = self.source.freq_range()
        frame = Frame([Axis(
            xmin=fmin, xmax=fmax, xfmt="freq", ymin=btm, ymax=top, offscale=self.offscale(rows, btm, top),
            image=Image(data[::-1], cmap=self.cmap), # matrix row 0 is the lowest level
            traces=self._traces(raw),
        )], title=f"{self.TITLE} - {len(rows)} FFTs", readout=self.rbw_readout(rows.shape[-1]))
        self.apply_markers(frame, image=True)
        return frame
