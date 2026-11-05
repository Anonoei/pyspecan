"""PlotPane: draws any Frame with matplotlib and builds the plot's settings panel

Plots know nothing about tk or matplotlib, they declare their settings and
return Frames. This is the only place the tk view draws them, so a new plot
in `pyspecan.plots` shows up here without any tk code.
"""
import tkinter as tk
from tkinter import ttk

import numpy as np

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from ...backend.mpl.color import cmap
from ...backend.mpl.plot import BlitPlot
from ...obj import Frequency
from ...plots import Scroller
from ...plots.frame import Axis, Frame, Image
from ...view.tkGUI.panels import Panel

def _signature(frame: Frame):
    """What decides the figure's layout, the figure is rebuilt when it changes"""
    return tuple((ax.projection, ax.image is not None, ax.square, ax.aspect) for ax in frame.axes)

class PlotPane:
    """One plot in a panel pane"""
    def __init__(self, ctrl, pane: Panel, pid: str):
        self.ctrl = ctrl
        self.pane = pane
        self.pid = pid
        self.plot = ctrl.plots.get(pid)
        self.plotter: BlitPlot | None = None
        self.canvas_widget = None
        self.sig = None
        self.scrollers: dict[int, Scroller] = {}
        self.images: dict[int, np.ndarray] = {} # full image per axis, scrolling images keep their history
        self.frame: Frame | None = None
        self.lim: dict[int, dict] = {}
        self.drawn: dict[int, set] = {}
        self.vars: dict[str, tk.Variable] = {}
        pane.master.config(text=self.plot.TITLE)

        self.btn_enable = ttk.Button(pane.master, text="DISABLE", style="Toggle.TButton", command=self.toggle)
        self.btn_enable.place(relx=1, rely=0, x=-100, y=5, anchor=tk.N, bordermode=tk.OUTSIDE, height=30, width=80)
        self.lbl_time = ttk.Label(pane.master, text="00.000s", style="Time.TLabel")
        self.lbl_time.place(relx=1, rely=0, x=-180, y=5, anchor=tk.N, bordermode=tk.OUTSIDE, height=20, width=60)

        self.fr_canv = ttk.Frame(pane.fr_main)
        self.fr_canv.pack(fill=tk.BOTH, expand=True)
        self.lbl_lo = ttk.Label(pane.fr_main, text="V")
        self.lbl_hi = ttk.Label(pane.fr_main, text="^")
        self.build_settings()

    # --- settings --- #
    def build_settings(self):
        """One widget per declared setting"""
        parent = self.pane.settings
        for child in parent.winfo_children():
            child.destroy()
        self.vars = {}
        values = self.plot.settings()
        for row, f in enumerate(self.plot.fields()):
            key, kind = f["key"], f["kind"]
            ttk.Label(parent, text=f["label"]).grid(row=row, column=0, sticky=tk.W)
            if kind == "check":
                var = tk.BooleanVar(parent, bool(values[key]))
                w = ttk.Checkbutton(parent, variable=var, command=lambda k=key: self.commit(k))
            elif kind == "select":
                var = tk.StringVar(parent, str(values[key]))
                w = ttk.Combobox(parent, textvariable=var, values=f["options"], state="readonly", width=9)
                w.bind("<<ComboboxSelected>>", lambda e, k=key: self.commit(k))
            else:
                var = tk.StringVar(parent, str(values[key]))
                w = ttk.Entry(parent, textvariable=var, width=10)
                w.bind("<Return>", lambda e, k=key: self.commit(k))
                w.bind("<FocusOut>", lambda e, k=key: self.refresh())
            self.vars[key] = var
            w.grid(row=row, column=1)

    def commit(self, key):
        """Apply a widget's value to the plot, the widgets show what the plot really holds afterwards"""
        try:
            self.ctrl.set_plot(self.pid, key, self.vars[key].get())
        except ValueError as e:
            self.ctrl.show_message(str(e))
        self.refresh()

    def refresh(self):
        values = self.plot.settings()
        for key, var in self.vars.items():
            var.set(values[key])

    def toggle(self):
        self.ctrl.set_plot(self.pid, "enabled", not self.plot.enabled)
        self.btn_enable.config(text="DISABLE" if self.plot.enabled else "ENABLE")

    def reset(self):
        self.scrollers.clear()
        self.images.clear()
        self.frame = None

    # --- drawing --- #
    def push(self, frame: Frame):
        """Take in a frame without drawing it, scrolling images must see every frame"""
        self.frame = frame
        for i, ax in enumerate(frame.axes):
            if ax.image is not None:
                self.images[i] = self.scrollers.setdefault(i, Scroller()).apply(ax.image)

    def render(self):
        """Draw the latest pushed frame"""
        frame = self.frame
        if frame is None:
            return
        sig = _signature(frame)
        if sig != self.sig:
            self._build(frame, sig)
        self.pane.master.config(text=frame.title or self.plot.TITLE)
        self.lbl_time.config(text=f"{frame.ptime:06.3f}s")
        offscale = {a.offscale for a in frame.axes}
        for lbl, which, rely in ((self.lbl_lo, "below", 0.9), (self.lbl_hi, "above", 0.1)):
            if which in offscale:
                lbl.place(relx=0.2, rely=rely, width=20, height=20)
                lbl.lift()
            elif lbl.winfo_ismapped():
                lbl.place_forget()
        for i, ax in enumerate(frame.axes):
            self._draw_axis(i, ax)
        self.plotter.update() # type: ignore
        self.frame = None

    def _build(self, frame: Frame, sig):
        if self.canvas_widget is not None:
            self.canvas_widget.destroy()
            plt.close(self.plotter.fig) # type: ignore
        fig = plt.figure(figsize=(5, 5), layout="constrained")
        fig.canvas = FigureCanvasTkAgg(fig, master=self.fr_canv)
        self.plotter = BlitPlot(fig) # type: ignore
        n = len(frame.axes)
        for i, ax in enumerate(frame.axes):
            mpl_ax = fig.add_subplot(n, 1, i + 1, projection="3d") if ax.projection == "3d" else fig.add_subplot(n, 1, i + 1)
            self.plotter.add_ax(i, mpl_ax)
            mpl_ax.set_autoscale_on(False)
            mpl_ax.grid(True, alpha=0.2)
            if ax.projection == "3d" and ax.aspect:
                mpl_ax.set_box_aspect(ax.aspect) # type: ignore
            elif ax.square:
                mpl_ax.set_box_aspect(1)
            if not ax.image:
                mpl_ax.locator_params(axis="x", nbins=5)
                mpl_ax.locator_params(axis="y", nbins=8)
        self.plotter.canvas.draw()
        self.canvas_widget = self.plotter.canvas.get_tk_widget() # type: ignore
        self.canvas_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.sig = sig
        self.lim = {}
        self.drawn = {}

    def _set_lim(self, i, name, lo, hi, setter, ticks=None):
        """Change an axis limit only when it changed, every change redraws the whole canvas"""
        cache = self.lim.setdefault(i, {})
        if cache.get(name) == (lo, hi):
            return
        cache[name] = (lo, hi)
        setter(lo, hi)
        if ticks is not None:
            ticks(lo, hi)

    def _auto(self, i, name, lo, hi, setter):
        """Limits for an axis the plot leaves to autorange: grow to fit, never shrink"""
        cur = self.lim.setdefault(i, {}).get(name)
        if cur is not None and cur[0] <= lo and cur[1] >= hi and (hi - lo) > 0.25 * (cur[1] - cur[0]):
            return
        pad = (hi - lo) * 0.05 or 0.5
        self._set_lim(i, name, lo - pad, hi + pad, setter)

    def _draw_axis(self, i: int, ax: Axis):
        mpl = self.plotter.ax(i) # type: ignore
        # x / y limits
        traces = ax.traces
        if ax.image is not None:
            xmin, xmax = (ax.xmin, ax.xmax) if ax.xmin is not None else (0.0, float(ax.image.data.shape[1]))
        else:
            xmin, xmax = ax.xmin, ax.xmax
        if xmin is not None and xmax is not None:
            self._set_lim(i, "x", xmin, xmax, mpl.set_xlim, (lambda lo, hi, ax=ax, mpl=mpl: self._freq_ticks(mpl, lo, hi)) if ax.xfmt == "freq" else None)
        elif traces:
            xs = [np.asarray(t.x) for t in traces if t.x is not None]
            if xs:
                self._auto(i, "x", min(float(x.min()) for x in xs), max(float(x.max()) for x in xs), mpl.set_xlim)
        if ax.ymin is not None and ax.ymax is not None:
            self._set_lim(i, "y", ax.ymin, ax.ymax, mpl.set_ylim)
        elif ax.image is None and traces:
            ys = [np.asarray(t.y) for t in traces]
            self._auto(i, "y", min(float(y.min()) for y in ys), max(float(y.max()) for y in ys), mpl.set_ylim)
        if ax.projection == "3d" and ax.zmin is not None:
            self._set_lim(i, "z", ax.zmin, ax.zmax, mpl.ax.set_zlim) # type: ignore
        if ax.ylabel:
            mpl.ax.set_ylabel(ax.ylabel)

        # artists
        names = set()
        for n, t in enumerate(traces):
            name = t.name or f"trace{n}"
            names.add(name)
            x = np.asarray(t.x) if t.x is not None else (np.linspace(xmin, xmax, len(t.y), endpoint=False) if xmin is not None and xmax is not None else np.arange(len(t.y)))
            if ax.projection == "3d":
                mpl.plot3d(x, t.y, t.z, name=name, color=t.color, linestyle="solid", linewidth=t.width, alpha=t.alpha)
            elif t.kind == "scatter":
                mpl.scatter(x, t.y, name=name, color=t.color, marker=".", linestyle="none", linewidth=0)
            else:
                mpl.plot(x, t.y, name=name, color=t.color, linewidth=t.width, alpha=t.alpha)
        if ax.image is not None:
            names.add("img")
            self._draw_image(i, ax, mpl, xmin, xmax)
        for name in self.drawn.get(i, set()) - names: # e.g. a hold trace that was switched off
            art = mpl.art(name)
            if art is not None:
                art.set_visible(False)
        for name in names:
            mpl.art(name).set_visible(True)
        self.drawn[i] = names

    def _freq_ticks(self, mpl, lo, hi):
        ticks = np.linspace(lo, hi, 5)
        mpl.ax.set_xticks(ticks, [str(Frequency.get(f)) for f in ticks])

    def _draw_image(self, i: int, ax: Axis, mpl, xmin, xmax):
        im: Image = ax.image # type: ignore
        data = self.images[i]
        rows = data.shape[0]
        top, btm = (ax.ymax, ax.ymin) if ax.ymin is not None else (0, rows)
        extent = (xmin, xmax, btm, top)
        art = mpl.art("img")
        if art is None:
            art = mpl.imshow(
                data, name="img", cmap=cmap[im.cmap], vmin=0, vmax=255, aspect="auto", extent=extent,
                interpolation="nearest", resample=False, rasterized=True,
            )
            if ax.ymin is not None: # a level axis gets a color bar, in relative hits
                bar = self.plotter.fig.colorbar(art, ax=mpl.ax, pad=0.005, fraction=0.05) # type: ignore
                bar.formatter = FuncFormatter(lambda v, _: f"{v/255:.1f}")
                bar.update_ticks()
                self.plotter.canvas.draw() # type: ignore
        else:
            art.set_data(data)
            if self.lim.get(i, {}).get("extent") != extent:
                art.set_extent(extent)
                self.lim.setdefault(i, {})["extent"] = extent
            if art.get_cmap().name != cmap[im.cmap].name:
                art.set_cmap(cmap[im.cmap])
        self.lim.setdefault(i, {})["extent"] = extent
        self._set_lim(i, "y", btm, top, mpl.set_ylim)

    def destroy(self):
        if self.plotter is not None:
            plt.close(self.plotter.fig)
        self.btn_enable.destroy()
        self.lbl_time.destroy()
        for child in self.pane.fr_main.winfo_children():
            child.destroy()
        for child in self.pane.settings.winfo_children():
            child.destroy()
