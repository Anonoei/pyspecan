"""PlotPane: draws any Frame with matplotlib and builds the plot's settings panel

Plots know nothing about tk or matplotlib, they declare their settings and
return Frames. This is the only place the tk view draws them, so a new plot
in `pyspecan.plots` shows up here without any tk code.
"""
import tkinter as tk
from tkinter import simpledialog, ttk

import numpy as np

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
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

def _log10_label(v: float) -> str:
    """y values holding log10 of the quantity: -3 -> 1e-3"""
    m, e = f"{10.0 ** v:.0e}".split("e")
    return f"{m}e{int(e)}"

class PlotPane:
    """One plot in a panel pane

    The widgets are rebuilt whenever plots are rearranged, so what must survive that (the latest
    frame, scrolling image histories) lives in `keep`, which the panel controller holds per plot.
    """
    def __init__(self, ctrl, pane: Panel, pid: str, keep: dict | None = None):
        self.ctrl = ctrl
        self.pane = pane
        self.pid = pid
        self.plot = ctrl.plots.get(pid)
        self.keep = keep if keep is not None else {}
        self.plotter: BlitPlot | None = None
        self.canvas_widget = None
        self.sig = None
        self.scrollers: dict[int, Scroller] = self.keep.setdefault("scrollers", {})
        self.images: dict[int, np.ndarray] = self.keep.setdefault("images", {}) # full image per axis
        self.dirty = self.keep.get("frame") is not None # a frame is waiting to be drawn
        self.lim: dict[int, dict] = {}
        self.drawn: dict[int, set] = {}
        self.vars: dict[str, tk.Variable] = {}
        pane.master.config(text=self.plot.TITLE)

        self.btn_enable = ttk.Button(pane.master, text="DISABLE", style="Toggle.TButton", command=self.toggle)
        self.btn_enable.place(relx=1, rely=0, x=-100, y=5, anchor=tk.N, bordermode=tk.OUTSIDE, height=30, width=80)
        self.lbl_time = ttk.Label(pane.master, text="00.000s", style="Time.TLabel")
        self.lbl_time.place(relx=1, rely=0, x=-180, y=5, anchor=tk.N, bordermode=tk.OUTSIDE, height=20, width=60)

        # packed first so the canvas can not take its space
        self.lbl_readout = ttk.Label(pane.fr_main, text="", justify=tk.LEFT, anchor=tk.W)
        self.lbl_readout.bind("<Configure>", lambda e: self.lbl_readout.config(wraplength=max(e.width, 50)))
        self.tree: ttk.Treeview | None = None # the marker table, built with the first rows
        self.tree_rows: list[str] = [] # marker id of every tree row
        self.table_sig = None
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
        if self.plot.MARKERS:
            self._marker_controls(parent, len(self.plot.fields()))

    # --- markers --- #
    def _marker_controls(self, parent, row):
        ttk.Label(parent, text="Add marker").grid(row=row, column=0, sticky=tk.W)
        var = tk.StringVar(parent, "")
        box = ttk.Combobox(parent, textvariable=var, values=list(self.plot.markers.kinds()), state="readonly", width=9)
        box.grid(row=row, column=1)
        def add(_e):
            self._marker_op(lambda: self.ctrl.add_marker(self.pid, var.get()))
            var.set("")
        box.bind("<<ComboboxSelected>>", add)
        ttk.Button(parent, text="Edit selected", command=self._edit_marker).grid(row=row + 1, column=0)
        ttk.Button(parent, text="Delete selected", command=lambda: self._marker_op(lambda: self.ctrl.del_marker(self.pid, self._selected()))).grid(row=row + 1, column=1)

    def _marker_op(self, fn):
        try:
            fn()
        except (ValueError, TypeError) as e:
            self.ctrl.show_message(str(e))
        self.table_sig = None # redraw the table with the next frame

    def _selected(self) -> str:
        if self.tree is None or not self.tree.selection():
            raise ValueError("select a marker in the table first")
        return self.tree_rows[int(self.tree.selection()[0])]

    def _edit_marker(self):
        """key=value for the selected marker's settings (see its kind in the marker command)"""
        try:
            mid = self._selected()
        except ValueError as e:
            self.ctrl.show_message(str(e))
            return
        item = self.plot.markers.items[mid]
        keys = ", ".join(f"{k}={v!r}" for k, v in item["params"].items())
        text = simpledialog.askstring(f"{mid} ({item['kind']})", f"key=value\n{keys}", parent=self.pane.master)
        if text and "=" in text:
            key, value = text.split("=", 1)
            self._marker_op(lambda: self.ctrl.set_marker(self.pid, mid, key.strip(), value.strip()))

    def _table(self, frame: Frame):
        t = frame.table
        sig = None if t is None else (tuple(t.columns), tuple((r.id, tuple(r.cells)) for r in t.rows))
        if sig == self.table_sig:
            return
        self.table_sig = sig
        if t is None or not t.rows:
            if self.tree is not None and self.tree.winfo_ismapped():
                self.tree.pack_forget()
            return
        if self.tree is None:
            self.tree = ttk.Treeview(self.pane.fr_main, show="headings", selectmode="browse")
            self.tree.bind("<<TreeviewSelect>>", lambda e: None)
        self.tree.config(columns=[str(i) for i in range(len(t.columns))], height=min(len(t.rows), 8))
        for i, name in enumerate(t.columns):
            self.tree.heading(str(i), text=name)
            self.tree.column(str(i), width=40 if i == 0 else 100, stretch=i == len(t.columns) - 1)
        keep = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        self.tree_rows, owner = [], ""
        for k, r in enumerate(t.rows):
            owner = r.id or owner
            self.tree_rows.append(owner)
            self.tree.insert("", tk.END, iid=str(k), values=r.cells)
        if keep and self.tree.exists(keep[0]):
            self.tree.selection_set(keep[0])
        if not self.tree.winfo_ismapped():
            self.tree.pack(side=tk.BOTTOM, fill=tk.X, before=self.fr_canv)

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
        self.keep["frame"] = None
        self.dirty = False

    # --- drawing --- #
    def push(self, frame: Frame):
        """Take in a frame without drawing it, scrolling images must see every frame"""
        self.keep["frame"] = frame
        self.dirty = True
        for i, ax in enumerate(frame.axes):
            if ax.image is not None:
                self.images[i] = self.scrollers.setdefault(i, Scroller()).apply(ax.image)

    def render(self):
        """Draw the latest pushed frame"""
        frame = self.keep.get("frame")
        if frame is None or not self.dirty:
            return
        sig = _signature(frame)
        if sig != self.sig:
            self._build(frame, sig)
        self.pane.master.config(text=frame.title or self.plot.TITLE)
        self.lbl_time.config(text=f"{frame.ptime:06.3f}s")
        self._readout(frame)
        self._table(frame)
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
        self.dirty = False

    def _readout(self, frame: Frame):
        text = "   ".join(f"{k}: {v}" for k, v in frame.readout)
        if text == self.lbl_readout.cget("text"):
            return
        self.lbl_readout.config(text=text)
        if text and not self.lbl_readout.winfo_ismapped():
            self.lbl_readout.pack(side=tk.BOTTOM, fill=tk.X, before=self.fr_canv)
        elif not text and self.lbl_readout.winfo_ismapped():
            self.lbl_readout.pack_forget()

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
        if self.lim.setdefault(i, {}).get("yfmt") != ax.yfmt:
            self.lim[i]["yfmt"] = ax.yfmt
            if ax.yfmt == "log10":
                mpl.ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: _log10_label(v)))
            else:
                mpl.ax.yaxis.set_major_formatter(plt.ScalarFormatter())

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
        names |= self._draw_marks(ax, mpl)
        for name in self.drawn.get(i, set()) - names: # e.g. a hold trace that was switched off
            art = mpl.art(name)
            if art is not None:
                art.set_visible(False)
        for name in names:
            mpl.art(name).set_visible(True)
        self.drawn[i] = names

    def _draw_marks(self, ax: Axis, mpl) -> set:
        """Bands and markers as named artists, reused between frames (blitting only draws registered artists)"""
        names = set()
        for n, b in enumerate(ax.bands):
            name = f"band{n}"
            art = mpl.art(name)
            if art is None:
                art = Rectangle((b.lo, 0), b.hi - b.lo, 1, transform=mpl.ax.get_xaxis_transform(), zorder=1)
                mpl.ax.add_patch(art)
                mpl.add_artist(name, art)
            art.set_xy((b.lo, 0))
            art.set_width(b.hi - b.lo)
            art.set_facecolor(b.color)
            art.set_alpha(b.alpha)
            art.set_edgecolor("none")
            names.add(name)
        for n, m in enumerate(ax.markers):
            if m.kind == "vline":
                name = f"vl{n}"
                art = mpl.art(name)
                if art is None:
                    art = mpl.plot([m.x, m.x], [0, 1], name=name, color=m.color, linewidth=1, transform=mpl.ax.get_xaxis_transform())
                art.set_data([m.x, m.x], [0, 1])
                art.set_color(m.color)
                names.add(name)
                continue
            name = f"mk{n}"
            art = mpl.art(name)
            if art is None:
                mpl.plot([m.x], [m.y], name=name, color=m.color, marker="v", linestyle="none", markersize=7, clip_on=True)
                txt = mpl.ax.text(m.x, m.y, m.label, color=m.color, fontsize=8, ha="left", va="bottom", clip_on=True)
                mpl.add_artist(f"mkt{n}", txt)
            art = mpl.art(name)
            art.set_data([m.x], [m.y])
            art.set_color(m.color)
            txt = mpl.art(f"mkt{n}")
            txt.set_position((m.x, m.y))
            txt.set_text(m.label)
            txt.set_color(m.color)
            names.update((name, f"mkt{n}"))
        return names

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

    def close(self):
        """Release the figure, the widgets go with their frame"""
        if self.plotter is not None:
            plt.close(self.plotter.fig)
            self.plotter = None
