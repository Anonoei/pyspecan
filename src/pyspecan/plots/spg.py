from collections import deque
from dataclasses import replace

import numpy as np

from .base import plot
from .freq import FreqPlot, SETTING_CMAP
from .frame import BLUE, IMAGE, LINE, THREE_D, YELLOW, Axis, Frame, Image, Surface, Trace
from .settings import Setting, override

class _Spectrogram(FreqPlot):
    """Spectrogram, newest on top. Subclasses pick how the block is framed (FRAMING) and reduced"""
    FEATURES = frozenset({IMAGE})
    FRAMING = "swept"
    SETTINGS = override(FreqPlot.SETTINGS, ref_level={"reset": True}, scale_div={"reset": True}) + (
        SETTING_CMAP,
        Setting("max_count", "History", "int", default=256, min=1, max=4096, reset=True, group="Display", hint="rows"),
    )

    def reset(self):
        super().reset()
        self._clear = True # tell the view to drop its history

    def raw_rows(self) -> np.ndarray:
        """The new rows of this tick (k, nfft), in dB, before the vbw"""
        raise NotImplementedError()

    def render(self):
        raw = self.raw_rows()
        if not len(raw):
            return None
        raw = raw[-self.max_count:]
        self.last = raw[-1] # what markers measure
        rows = self.smooth(raw)
        btm, top = self.y_range(rows)
        data = (np.clip((rows - btm) / (top - btm), 0.0, 1.0) * 255).astype(np.uint8)
        clear, self._clear = self._clear, False
        fmin, fmax = self.source.freq_range()
        frame = Frame([Axis(
            xmin=fmin, xmax=fmax, xfmt="freq", ylabel="sweeps",
            image=Image(data, cmap=self.cmap, scroll=True, rows=self.max_count, clear=clear),
        )], title=self.TITLE, readout=self.rbw_readout(rows.shape[-1]))
        self.apply_markers(frame, image=True)
        return frame

@plot("Spectrogram")
class SPG(_Spectrogram):
    """One row per refresh: the last swept frame of the block, the trace the PSD plot draws"""
    TITLE = "Spectrogram"

    def raw_rows(self):
        return self.psd_rows("swept", smooth=False)[-1:]

@plot("RT Spectrogram")
class RTSPG(_Spectrogram):
    """One row per block: the mean of its overlapped (realtime) frames"""
    TITLE = "RT Spectrogram"

    def raw_rows(self):
        rows = self.psd_rows("rt", smooth=False)
        return rows.mean(axis=0, keepdims=True) if len(rows) else rows

@plot("3D Spectrogram")
class SPG3D(FreqPlot):
    """A waterfall in 3d: the last rows as lines over frequency (x), age (y) and level (z), newest in front.
    Markers measure the newest row, channel bands lie on the floor"""
    TITLE = "3D Spectrogram"
    FEATURES = frozenset({LINE, THREE_D})
    SETTINGS = FreqPlot.SETTINGS + (
        Setting("framing", "Rows", "select", default="swept", options=("swept", "rt"), reset=True, group="Display",
                help="swept: the last frame of each refresh, rt: the mean of the block's overlapped frames"),
        Setting("max_count", "History", "int", default=32, min=2, max=256, reset=True, group="Display", hint="rows"),
        Setting("points", "Points", "int", default=256, min=16, max=4096, step=64, group="Display", advanced=True,
                help="display points per row (peak detector)"),
    )

    def reset(self):
        super().reset()
        self.rows: deque = deque(maxlen=self.max_count) # (x, y) of the reduced rows, newest first

    def render(self):
        raw = self.psd_rows("swept" if self.framing == "swept" else "rt", smooth=False)
        if not len(raw):
            return None
        self.last = raw[-1] if self.framing == "swept" else raw.mean(axis=0)
        x, y = self.reduced(self.smooth(self.last), self.points)
        if self.rows and len(self.rows[0][1]) != len(y): # the fft size changed
            self.rows.clear()
        self.rows.appendleft((x, y))
        btm, top = self.y_range(self.last)
        fmin, fmax = self.source.freq_range()
        traces = []
        for age in range(len(self.rows) - 1, -1, -1): # oldest (at the back) first, the newest drawn last
            rx, ry = self.rows[age]
            if rx is None:
                rx = fmin + np.arange(len(ry)) * ((fmax - fmin) / len(ry))
            newest = age == 0
            traces.append(Trace(np.full(len(ry), float(age)), rx, z=np.clip(ry, btm, top), name=f"r{age}",
                                color=YELLOW if newest else BLUE, width=1.5 if newest else 1.0,
                                alpha=1.0 if newest else max(0.15, 0.8 * (1 - age / self.max_count))))
        frame = Frame([Axis(
            xmin=fmin, xmax=fmax, xfmt="freq", ymin=0, ymax=self.max_count - 1, zmin=btm, zmax=top,
            ylabel="rows ago", projection="3d", aspect=(2.0, 1.2, 0.7), traces=traces,
        )], title=self.TITLE, readout=self.rbw_readout(len(self.last)))
        self.apply_markers(frame)
        frame.axes[0].bands = [replace(b, ylo=None, yhi=None) for b in frame.axes[0].bands] # y is age here, not level
        return frame

@plot("Surface Spectrogram")
class SurfaceSpectrogram(FreqPlot):
    """A 3d surface spectrogram: the spectrogram as a solid surface over frequency (x) and age (y), its height and its
    color the level, newest in front. Turn it to look along the time or the frequency axis. Channel bands lie on the
    floor, markers measure the newest row"""
    TITLE = "Surface Spectrogram"
    FEATURES = frozenset({THREE_D})
    SETTINGS = FreqPlot.SETTINGS + (
        SETTING_CMAP,
        Setting("framing", "Rows", "select", default="swept", options=("swept", "rt"), reset=True, group="Display",
                help="swept: the last frame of each refresh, rt: the mean of the block's overlapped frames"),
        Setting("max_count", "History", "int", default=64, min=4, max=512, reset=True, group="Display", hint="rows"),
        Setting("points", "Points", "int", default=192, min=16, max=2048, step=32, reset=True, group="Display", advanced=True,
                help="cells across the frequency axis (peak detector)"),
    )

    def reset(self):
        super().reset()
        self.rows: deque = deque(maxlen=self.max_count) # reduced rows in dB, newest first

    def render(self):
        raw = self.psd_rows("swept" if self.framing == "swept" else "rt", smooth=False)
        if not len(raw):
            return None
        self.last = raw[-1] if self.framing == "swept" else raw.mean(axis=0)
        _, y = self.reduced(self.smooth(self.last), self.points)
        if self.rows and len(self.rows[0]) != len(y):
            self.rows.clear()
        self.rows.appendleft(y)
        btm, top = self.y_range(self.last)
        fmin, fmax = self.source.freq_range()
        grid = np.array(self.rows) # (age, cols), age 0 the newest: row 0 at y = 0, in front
        data = (np.clip((grid - btm) / (top - btm), 0.0, 1.0) * 255).astype(np.uint8)
        frame = Frame([Axis(
            xmin=fmin, xmax=fmax, xfmt="freq", ymin=0, ymax=max(len(self.rows) - 1, 1), zmin=btm, zmax=top,
            ylabel="rows ago", projection="3d", aspect=(2.0, 1.4, 0.7), surface=Surface(data, self.cmap),
        )], title=self.TITLE, readout=self.rbw_readout(len(self.last)))
        self.apply_markers(frame)
        ax = frame.axes[0]
        ax.bands = [replace(b, ylo=None, yhi=None) for b in ax.bands] # y is age here, not level
        ax.markers = [] # points in 3d are not drawn: the table has them
        return frame
