"""PlotPane: draws any Frame with matplotlib and builds the plot's settings panel

Plots know nothing about tk or matplotlib, they declare their settings and
return Frames. This is the only place the tk view draws them, so a new plot
in `pyspecan.plots` shows up here without any tk code.
"""
import tkinter as tk
from tkinter import simpledialog, ttk

import numpy as np

from matplotlib.figure import Figure
from matplotlib.ticker import ScalarFormatter
from matplotlib.patches import Rectangle
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib.ticker import FuncFormatter
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from ...backend.mpl.color import cmap
from ...backend.mpl.plot import BlitPlot
from ...obj import Frequency
from ...plots import Scroller
from ...plots.drag import MIN_DRAG_PX, TOOLS, Drag, commit, hit_test, preview, settled
from ...plots.freq import fmt_hz
from ...plots.frame import Axis, Frame, Image, fmt_time
from ...view.tkGUI.panels import Panel

def _signature(frame: Frame):
    """What decides the figure's layout, the figure is rebuilt when it changes"""
    return tuple((ax.projection, ax.image is not None, ax.square, ax.aspect) for ax in frame.axes)

def _log10_label(v: float) -> str:
    """y values holding log10 of the quantity: -3 -> 1e-3"""
    m, e = f"{10.0 ** v:.0e}".split("e")
    return f"{m}e{int(e)}"

MARK_TOP_PX = 22 # a point marker's triangle stays this far below the top, so its label shows

def _mark_y(ax, v: float) -> float:
    """The level a point marker's triangle is drawn at: on the plot even when its level is off the range"""
    lo, hi = sorted(ax.get_ylim())
    v = float(min(max(v, lo), hi)) if np.isfinite(v) else float(lo)
    top = ax.transData.transform((0.0, hi))[1] - MARK_TOP_PX
    if ax.transData.transform((0.0, v))[1] > top:
        v = float(ax.transData.inverted().transform((0.0, top))[1])
    return v

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
        self.drag: Drag | None = None # a marker being drawn, moved or resized with the mouse
        self.hover: tuple[int, float, float] | None = None # (axis, x, y pixels) of the pointer over an axis
        self.keep.setdefault("tool", TOOLS[0])
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
        """The link picker, then one collapsible section per settings group (rarely used ones folded under
        "Advanced"), then the markers"""
        parent = self.pane.settings
        for child in parent.winfo_children():
            child.destroy()
        self.vars = {}
        values = self.plot.settings()
        linked = self.plot.link is not None
        self._link_picker(parent)
        groups: dict[str, list[dict]] = {}
        for f in self.plot.fields():
            groups.setdefault(f["group"], []).append(f)
        for name, fields in groups.items():
            body = self._section(parent, name)
            basic = [f for f in fields if not f["advanced"]]
            adv = [f for f in fields if f["advanced"]]
            for row, f in enumerate(basic):
                self._field(body, row, f, values, linked)
            if adv:
                more = self._section(body, f"{name} advanced", text="Advanced", row=len(basic), default=False)
                for row, f in enumerate(adv):
                    self._field(more, row, f, values, linked)
        if self.plot.MARKERS:
            body = self._section(parent, "Markers")
            self._marker_controls(body, 0)

    def _section(self, parent, key: str, text: str | None = None, row: int | None = None, default=True) -> ttk.Frame:
        """A titled section whose body the title button shows and hides, open state survives rebuilds"""
        opened = self.keep.setdefault("sections", {})
        opened.setdefault(key, default)
        outer = ttk.Frame(parent)
        if row is None:
            outer.pack(side=tk.TOP, fill=tk.X, pady=(2, 0))
        else:
            outer.grid(row=row, column=0, columnspan=2, sticky=tk.EW)
        body = ttk.Frame(outer, padding=(8, 0, 0, 2))
        btn = ttk.Button(outer, style="Toolbutton")
        def show():
            btn.config(text=("▾ " if opened[key] else "▸ ") + (text or key))
            if opened[key]:
                body.pack(side=tk.TOP, fill=tk.X)
            else:
                body.pack_forget()
        def toggle():
            opened[key] = not opened[key]
            show()
        btn.config(command=toggle)
        btn.pack(side=tk.TOP, anchor=tk.W)
        show()
        return body

    def _field(self, parent, row: int, f: dict, values: dict, linked: bool):
        key, kind = f["key"], f["kind"]
        label = f["label"] + (" 🔗" if linked and f["scope"] == "link" else "")
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W)
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

    def _link_picker(self, parent):
        """Link this plot to another of its domain, they then share level / processing settings and markers"""
        plots = self.ctrl.plots
        targets = plots.linkable(self.pid)
        if not targets and self.plot.link is None:
            return
        fr = ttk.Frame(parent)
        fr.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(fr, text="Link").grid(row=0, column=0, sticky=tk.W)
        names = {f"{t} {plots.get(t).NAME}": t for t in targets}
        link = self.plot.link
        current = f"{link.id}: " + ", ".join(m for m in link.members if m != self.pid) if link else "none"
        var = tk.StringVar(fr, current)
        box = ttk.Combobox(fr, textvariable=var, values=["none", *names], state="readonly", width=12)
        box.grid(row=0, column=1)
        def pick(_e):
            choice = var.get()
            try:
                if choice == "none":
                    self.ctrl.unlink_plot(self.pid)
                elif choice in names:
                    self.ctrl.link_plot(self.pid, names[choice])
            except ValueError as e:
                self.ctrl.show_message(str(e))
            self.ctrl.when_idle(self.ctrl.panels.rebuild_settings)
        box.bind("<<ComboboxSelected>>", pick)

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
        ttk.Label(parent, text="Draw").grid(row=row + 2, column=0, sticky=tk.W)
        tool = tk.StringVar(parent, self.keep["tool"])
        draw = ttk.Combobox(parent, textvariable=tool, values=list(TOOLS), state="readonly", width=9)
        draw.grid(row=row + 2, column=1)
        draw.bind("<<ComboboxSelected>>", lambda _e: self.keep.__setitem__("tool", tool.get()))
        self.vars["_tool"] = tool

    def _marker_op(self, fn) -> bool:
        """Run a marker change, showing what went wrong, True when it worked"""
        ok = True
        try:
            fn()
        except (ValueError, TypeError) as e:
            self.ctrl.show_message(str(e))
            ok = False
        self.table_sig = None # redraw the table with the next frame
        return ok

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
        """Apply a widget's value to the plot, the widgets (of every plot, linked ones follow) show what the plots really hold afterwards"""
        try:
            self.ctrl.set_plot(self.pid, key, self.vars[key].get())
        except ValueError as e:
            self.ctrl.show_message(str(e))
        self.ctrl.panels.refresh()

    def refresh(self):
        self.plot = self.ctrl.plots.get(self.pid)
        values = self.plot.settings()
        for key, var in self.vars.items():
            if key in values:
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
        d = self.drag
        if d is not None and d.committed and d.i < len(frame.axes) and settled(frame.axes[d.i], d):
            self.drag = None
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
            self._draw_axis(i, preview(ax, self.drag, i))
        self._draw_hover(frame)
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
        # no pyplot: it would also make a canvas for its default backend (a hidden gtk window, say)
        fig = Figure(figsize=(5, 5), layout="constrained")
        FigureCanvasTkAgg(fig, master=self.fr_canv) # becomes fig.canvas
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
        for name, fn in (("button_press_event", self._on_press), ("motion_notify_event", self._on_motion),
                         ("button_release_event", self._on_release), ("figure_leave_event", self._on_leave)):
            fig.canvas.mpl_connect(name, fn)
        self.drag = self.hover = None
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
            self._set_lim(i, "x", xmin, xmax, mpl.set_xlim, self._x_ticks(ax, mpl))
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
            elif ax.yfmt == "freq":
                mpl.ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: fmt_hz(v)))
            else:
                mpl.ax.yaxis.set_major_formatter(ScalarFormatter())

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
        if ax.projection == "3d":
            return self._draw_bands_3d(ax, mpl)
        level = ax.image is None or ax.ymin is not None # a y span means something
        for n, b in enumerate(ax.bands):
            name = f"band{n}"
            art = mpl.art(name)
            if art is None:
                art = Rectangle((b.lo, 0), b.hi - b.lo, 1, zorder=1)
                mpl.ax.add_patch(art)
                mpl.add_artist(name, art)
            if level and (b.ylo is not None or b.yhi is not None):
                lo, hi = sorted(mpl.ax.get_ylim())
                y0 = lo if b.ylo is None else b.ylo
                y1 = hi if b.yhi is None else b.yhi
                art.set_transform(mpl.ax.transData)
            else: # the whole height
                y0, y1 = 0.0, 1.0
                art.set_transform(mpl.ax.get_xaxis_transform())
            art.set_xy((b.lo, y0))
            art.set_width(b.hi - b.lo)
            art.set_height(y1 - y0)
            art.set_facecolor(b.color)
            art.set_alpha(b.alpha)
            art.set_edgecolor("none")
            names.add(name)
        for n, m in enumerate(ax.markers):
            if m.kind == "hline":
                name, tname = f"hl{n}", f"hlt{n}"
                tr = mpl.ax.get_yaxis_transform() # x in axes fractions, y in data
                if mpl.art(name) is None:
                    mpl.plot([0, 1], [m.y, m.y], name=name, color=m.color, linewidth=1, linestyle=(0, (6, 3)), transform=tr)
                    mpl.add_artist(tname, mpl.ax.text(0.995, m.y, m.label, color=m.color, fontsize=8, ha="right", va="bottom",
                                                      transform=tr, clip_on=True))
                mpl.art(name).set_data([0, 1], [m.y, m.y])
                mpl.art(name).set_color(m.color)
                txt = mpl.art(tname)
                txt.set_position((0.995, m.y))
                txt.set_text(m.label)
                txt.set_color(m.color)
                names.update((name, tname))
                continue
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
            y = _mark_y(mpl.ax, m.y) # a marker off the level range sits at the edge, as in the web view
            art.set_data([m.x], [y])
            art.set_color(m.color)
            txt = mpl.art(f"mkt{n}")
            txt.set_position((m.x, y))
            txt.set_text(m.label)
            txt.set_color(m.color)
            names.update((name, f"mkt{n}"))
        return names

    def _draw_bands_3d(self, ax: Axis, mpl) -> set:
        """Bands on a 3d axis: boxes on the x / y floor (at zmin), the y span defaulting to the y range"""
        names = set()
        ylo, yhi = (ax.ymin, ax.ymax) if ax.ymin is not None else sorted(mpl.ax.get_ylim())
        z = ax.zmin if ax.zmin is not None else min(mpl.ax.get_zlim()) # type: ignore
        for n, b in enumerate(ax.bands):
            name = f"band3d{n}"
            y0 = ylo if b.ylo is None else b.ylo
            y1 = yhi if b.yhi is None else b.yhi
            verts = [[(b.lo, y0, z), (b.hi, y0, z), (b.hi, y1, z), (b.lo, y1, z)]]
            art = mpl.art(name)
            if art is None:
                art = Poly3DCollection(verts)
                mpl.ax.add_collection3d(art) # type: ignore
                mpl.add_artist(name, art)
            art.set_verts(verts)
            art.set_facecolor(b.color)
            art.set_edgecolor(b.color)
            art.set_alpha(b.alpha)
            names.add(name)
        return names

    # --- mouse: draw, move and resize markers (the logic is plots/drag.py, shared in spirit with the web view) --- #
    def _mouse_axis(self, event) -> int:
        """Index of the 2d axis under the pointer, -1 for none"""
        frame = self.keep.get("frame")
        if self.plotter is None or frame is None or event.inaxes is None:
            return -1
        for i, ax in enumerate(frame.axes):
            if ax.projection == "2d" and self.plotter.ax(i).ax is event.inaxes:
                return i
        return -1

    def _can_draw(self, i: int) -> bool:
        """Can new markers be drawn on axis i (a frequency axis of a plot with markers)"""
        frame = self.keep.get("frame")
        return i >= 0 and frame is not None and self.plot.MARKERS and frame.axes[i].xfmt == "freq"

    def _hit(self, i: int, event) -> Drag | None:
        """The draggable mark under the pointer on axis i"""
        if i < 0:
            return None
        return hit_test(self.keep["frame"].axes[i], i, self._to_px(i), event.x, event.y, self._to_py(i), self._level_py(i))

    def _to_px(self, i: int):
        tr = self.plotter.ax(i).ax.transData # type: ignore
        return lambda v: float(tr.transform((v, 0.0))[0])

    def _to_py(self, i: int):
        frame = self.keep["frame"]
        if frame.axes[i].image is not None and frame.axes[i].ymin is None: # time rows, markers span them
            return None
        ax = self.plotter.ax(i).ax # type: ignore
        return lambda v: float(ax.transData.transform((0.0, _mark_y(ax, v)))[1]) # where the triangle is drawn

    def _level_py(self, i: int):
        """data y -> pixel y, None on an axis without levels"""
        frame = self.keep["frame"]
        if frame.axes[i].image is not None and frame.axes[i].ymin is None:
            return None
        tr = self.plotter.ax(i).ax.transData # type: ignore
        return lambda v: float(tr.transform((0.0, v))[1])

    def _data_xy(self, i: int, px: float, py: float) -> tuple[float, float]:
        """Pixel -> data, clamped to the axis"""
        ax = self.plotter.ax(i).ax # type: ignore
        x, y = ax.transData.inverted().transform((px, py))
        (x0, x1), (y0, y1) = sorted(ax.get_xlim()), sorted(ax.get_ylim())
        return float(min(max(x, x0), x1)), float(min(max(y, y0), y1))

    def _cursor(self, name: str):
        if self.canvas_widget is not None and str(self.canvas_widget.cget("cursor")) != name:
            self.canvas_widget.config(cursor=name)

    def _on_press(self, event):
        if event.button != 1 or self.drag is not None:
            return
        i = self._mouse_axis(event)
        if i < 0:
            return
        d = self._hit(i, event)
        x, y = self._data_xy(i, event.x, event.y)
        if d is None:
            if self.keep["tool"] == "off" or not self._can_draw(i):
                return
            d = Drag(i, "new", x, x)
        d.start = y if d.mode == "level" else x
        self.drag = d
        if d.mode == "move":
            self._cursor("fleur")

    def _on_motion(self, event):
        d = self.drag
        if d is not None and not d.committed:
            x, y = self._data_xy(d.i, event.x, event.y)
            if d.mode == "level":
                d.to(x, event.y - self._level_py(d.i)(d.start), y) # type: ignore[misc]
            else:
                d.to(x, event.x - self._to_px(d.i)(d.start))
            self.hover = (d.i, event.x, event.y)
            self._redraw()
            return
        i = self._mouse_axis(event)
        self.hover = (i, event.x, event.y) if i >= 0 else None
        cursor = ""
        hit = self._hit(i, event)
        if hit is not None:
            cursor = {"move": "fleur", "level": "sb_v_double_arrow"}.get(hit.mode, "sb_h_double_arrow")
        elif self._can_draw(i) and self.keep["tool"] != "off":
            cursor = "crosshair"
        self._cursor(cursor)
        self._redraw()

    def _on_release(self, event):
        d = self.drag
        if event.button != 1 or d is None or d.committed:
            return
        to_px = self._to_px(d.i)
        lo, hi = d.span
        action = commit(self.keep["tool"], d, abs(to_px(hi) - to_px(lo)) >= MIN_DRAG_PX)
        if action is None:
            self.drag = None
        else:
            d.committed = True # keep showing where it was dropped until a frame shows it (or a moment passes)
            op, what, params = action
            if op == "add":
                ok = self._marker_op(lambda: self.ctrl.add_marker(self.pid, what, **params))
            elif op == "plot":
                ok = self._marker_op(lambda: self._set_plot(params))
            else:
                ok = self._marker_op(lambda: self.ctrl.set_marker_params(self.pid, what, params))
            if not ok:
                self.drag = None
            else:
                self.pane.master.after(1500, lambda: self._expire(d))
        self._cursor("")
        self._redraw()

    def _set_plot(self, params: dict):
        """A dragged mark of the plot itself: its settings, the settings panel follows"""
        for key, value in params.items():
            self.ctrl.set_plot(self.pid, key, value)
        self.ctrl.panels.refresh()

    def _expire(self, d: Drag):
        if self.drag is d:
            self.drag = None
            self._redraw()

    def _on_leave(self, _event):
        self.hover = None
        if self.drag is None:
            self._cursor("")
            self._redraw()

    def _redraw(self):
        """Draw the latest frame again, with the drag and hover readout, between frames"""
        frame = self.keep.get("frame")
        if frame is None or self.plotter is None or _signature(frame) != self.sig:
            return
        for i, ax in enumerate(frame.axes):
            self._draw_axis(i, preview(ax, self.drag, i))
        self._draw_hover(frame)
        self.plotter.update()

    def _hover_text(self, frame: Frame, i: int, x: float, y: float) -> str:
        ax = frame.axes[i]
        if ax.xfmt == "freq":
            fx, name = fmt_hz, "f"
        elif ax.xfmt == "time":
            x0, x1 = self.plotter.ax(i).ax.get_xlim() # type: ignore
            fx, name = (lambda v: fmt_time(v, x1 - x0)), "t"
        else:
            fx, name = (lambda v: f"{v:.4g}"), "x"
        d = self.drag
        if d is not None and d.i == i and d.mode not in ("marker", "level"):
            lo, hi = d.span
            lines = [f"{fx(lo)} – {fx(hi)}", f"width {fx(hi - lo)}   center {fx((lo + hi) / 2)}"]
        else:
            lines = [f"{name} {fx(x)}"]
        if ax.image is None:
            unit = str(getattr(self.plot, "unit", "") or "")
            fy = _log10_label if ax.yfmt == "log10" else fmt_hz if ax.yfmt == "freq" else (lambda v: f"{v:.2f}")
            lines.append(f"cursor {fy(y)} {unit}".strip())
            if ax.traces and d is None:
                t = ax.traces[-1] # the plot's own trace is the last one
                ty = np.asarray(t.y)
                if len(ty):
                    if t.x is not None:
                        k = int(np.argmin(np.abs(np.asarray(t.x) - x)))
                    else:
                        x0, x1 = self.plotter.ax(i).ax.get_xlim() # type: ignore
                        k = int(round((x - x0) / ((x1 - x0) or 1.0) * len(ty))) # spaced as _draw_axis draws them
                    lines.append(f"trace  {fy(float(ty[min(max(k, 0), len(ty) - 1)]))} {unit}".strip())
        return "\n".join(lines)

    def _draw_hover(self, frame: Frame):
        """Dashed crosshair and a readout of the pointer, named artists so blitting draws them"""
        for i, ax in enumerate(frame.axes):
            if ax.projection != "2d":
                continue
            mpl = self.plotter.ax(i) # type: ignore
            show = self.hover is not None and self.hover[0] == i
            if mpl.art("hov_t") is None:
                if not show:
                    continue
                style = dict(color="white", alpha=0.35, linewidth=1, linestyle=(0, (3, 3)))
                mpl.add_artist("hov_v", mpl.ax.axvline(0, **style))
                mpl.add_artist("hov_h", mpl.ax.axhline(0, **style))
                mpl.add_artist("hov_t", mpl.ax.text(0.99, 0.98, "", transform=mpl.ax.transAxes, ha="right", va="top",
                                                    fontsize=8, color="#eee", zorder=5,
                                                    bbox=dict(facecolor="#0a0a0a", alpha=0.8, edgecolor="#555")))
            v, h, t = mpl.art("hov_v"), mpl.art("hov_h"), mpl.art("hov_t")
            if not show:
                for art in (v, h, t):
                    art.set_visible(False)
                continue
            x, y = self._data_xy(i, self.hover[1], self.hover[2]) # type: ignore
            v.set_xdata([x, x])
            h.set_ydata([y, y])
            t.set_text(self._hover_text(frame, i, x, y))
            v.set_visible(True)
            h.set_visible(ax.image is None)
            t.set_visible(True)

    def _x_ticks(self, ax: Axis, mpl):
        """What to do with the x ticks when the x range changes"""
        if ax.xfmt == "freq":
            return lambda lo, hi: self._freq_ticks(mpl, lo, hi)
        if ax.xfmt == "time": # one unit for every tick, picked from the span
            return lambda lo, hi: mpl.ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: fmt_time(v, hi - lo)))
        return None

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
        self.plotter = None
