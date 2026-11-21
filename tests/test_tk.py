"""tkGUI: adding plots from the dropdown and rearranging them by dragging. Needs a display (xvfb-run)."""
import sys
import time

import numpy as np
import pytest

tk = pytest.importorskip("tkinter")
pytest.importorskip("matplotlib")

from pyspecan.config import Sink, View
from pyspecan.controller.controller import GetController
from pyspecan.model.model import GetModel
from pyspecan.view.view import GetView


@pytest.fixture
def app(tmp_path):
    path = tmp_path / "capture.cf64"
    t = np.arange(20000) / 10000
    np.exp(2j*np.pi*1000*t).astype(np.complex64).tofile(path)
    kw = dict(path=str(path), fmt="cf64", Fs="10k", nfft=256)
    model = GetModel(Sink.FILE)(**kw)
    try:
        view = GetView(View.tkGUI, Sink.FILE)(**kw)
    except tk.TclError:
        pytest.skip("no display")
    ctrl = GetController(View.tkGUI, Sink.FILE)(model, view, **kw)
    view.root.geometry("1200x800")
    errors = []
    view.root.report_callback_exception = lambda *a: errors.append(a)
    yield ctrl
    ctrl.quit()
    assert not errors, errors

def settle(ctrl, n=6):
    for _ in range(n):
        ctrl.view.root.update()

def wait_for(ctrl, cond, seconds=5.0):
    """Run the event loop until `cond()`: frames reach the panes on a timer"""
    end = time.monotonic() + seconds
    while not cond() and time.monotonic() < end:
        ctrl.view.root.update()
        time.sleep(0.01)
    assert cond()

def layout(ctrl):
    return [[ctrl.plots.get(p).NAME for p in row] for row in ctrl.plots.layout]

def ids(ctrl):
    return {ctrl.plots.get(p).NAME: p for row in ctrl.plots.layout for p in row}

def add(ctrl, name):
    sub, k = ctrl.add_menu_items[name] # its entry in the "+ Add plot" menu's category submenu
    sub.invoke(k) # the real command
    settle(ctrl)

def drag(ctrl, pid, target, where):
    """Press on a plot's grip, move over `where` of the target, release: like the mouse"""
    grip = ctrl.panels.panes[pid].pane.lbl_grip
    frame = next(f for f, p in ctrl.panels.frames.items() if p == target)
    x, y, w, h = frame.winfo_rootx(), frame.winfo_rooty(), frame.winfo_width(), frame.winfo_height()
    at = {"left": (.1, .5), "right": (.9, .5), "above": (.5, .1), "below": (.5, .9)}[where]
    pos = dict(rootx=int(x + w*at[0]), rooty=int(y + h*at[1]))
    grip.event_generate("<ButtonPress-1>", x=3, y=3, rootx=grip.winfo_rootx() + 3, rooty=grip.winfo_rooty() + 3)
    grip.event_generate("<B1-Motion>", x=3, y=3, **pos)
    grip.event_generate("<ButtonRelease-1>", x=3, y=3, **pos)
    settle(ctrl)

def test_the_add_menu_groups_the_plots_and_adds_one(app):
    menu = app.view.tb_menu_add
    cats = [menu.entrycget(k, "label") for k in range(menu.index("end") + 1)]
    assert cats == [c for c, _ in app.plot_groups()] and cats[:2] == ["Spectrum", "Time-frequency"]
    assert sorted(app.add_menu_items) == sorted(app.plot_types) # every plot, once
    sub, k = app.add_menu_items["Persistence"]
    posted = sys.platform != "win32" # posting on Windows enters the native menu loop, which blocks until dismissed
    if posted:
        sub.post(10, 10) # select its entry like the pointer would: what it does shows beside the menu
    sub.activate(k)
    sub.event_generate("<<MenuSelect>>")
    settle(app)
    text = app.tooltip.label.cget("text")
    assert text.startswith("Persistence (Spectrum)") and "Data:" in text and "Use:" in text and "heavy" in text
    if posted:
        sub.unpost()
    assert layout(app) == [["PSD"]]
    add(app, "Spectrogram")
    assert layout(app) == [["PSD"], ["Spectrogram"]]
    pane = app.panels.panes[ids(app)["PSD"]].pane
    pane.lbl_grip.event_generate("<Enter>") # the plot's grip says what it does too
    settle(app)
    assert app.tooltip.label.cget("text").startswith("PSD (Spectrum)")
    pane.lbl_grip.event_generate("<Leave>")
    app.add_from_menu("not a plot")
    settle(app)
    assert layout(app) == [["PSD"], ["Spectrogram"]]

def test_dragging_rearranges(app):
    add(app, "Spectrogram"); add(app, "IQ"); add(app, "FFT")
    i = ids(app)
    drag(app, i["IQ"], i["PSD"], "right")
    assert layout(app) == [["PSD", "IQ"], ["Spectrogram"], ["FFT"]]
    drag(app, i["FFT"], i["Spectrogram"], "left")
    assert layout(app) == [["PSD", "IQ"], ["FFT", "Spectrogram"]]
    drag(app, i["Spectrogram"], i["PSD"], "above")
    assert layout(app) == [["Spectrogram"], ["PSD", "IQ"], ["FFT"]]
    drag(app, i["PSD"], i["FFT"], "below")
    assert layout(app) == [["Spectrogram"], ["IQ"], ["FFT"], ["PSD"]]
    drag(app, i["IQ"], i["IQ"], "left")                 # onto itself: nothing
    assert layout(app) == [["Spectrogram"], ["IQ"], ["FFT"], ["PSD"]]
    assert app.panels.overlay.winfo_manager() == ""     # the drop indicator is gone

def test_a_drop_outside_any_plot_does_nothing(app):
    add(app, "IQ")
    i = ids(app)
    grip = app.panels.panes[i["IQ"]].pane.lbl_grip
    grip.event_generate("<ButtonPress-1>", x=3, y=3)
    grip.event_generate("<B1-Motion>", x=3, y=3, rootx=5000, rooty=5000)
    grip.event_generate("<ButtonRelease-1>", x=3, y=3, rootx=5000, rooty=5000)
    settle(app)
    assert layout(app) == [["PSD"], ["IQ"]]

def test_a_move_keeps_what_the_plots_showed(app):
    add(app, "Spectrogram")
    app.command("next"); app.command("next")
    i = ids(app)
    pane = app.panels.panes[i["Spectrogram"]]
    wait_for(app, lambda: 0 in pane.keep["images"])
    history = pane.keep["images"][0].copy()
    assert history.any()
    drag(app, i["Spectrogram"], i["PSD"], "right")
    new = app.panels.panes[i["Spectrogram"]]
    assert new is not pane and (new.keep["images"][0] == history).all()
    assert new.plotter is not None and new.plotter.fig.axes   # redrawn without waiting for a new frame
    assert len(app.panels.panes) == 2

def test_settings_state_and_closing(app):
    add(app, "IQ")
    i = ids(app)
    app.panels.toggle_settings(i["IQ"])                  # hide the settings
    drag(app, i["IQ"], i["PSD"], "left")
    assert not app.panels.panes[i["IQ"]].pane.fr_sets.winfo_manager()   # still hidden after the move
    app.panels.panes[i["IQ"]].pane.btn_close.invoke()
    settle(app)
    assert layout(app) == [["PSD"]] and i["IQ"] not in app.panels.keep

def test_markers_draw_on_psd_and_spectrogram_with_a_table(app):
    add(app, "Spectrogram")
    i = ids(app)
    app.set_plot(i["PSD"], "unit", "dBFS")
    app.add_marker(i["PSD"], "peak")
    app.add_marker(i["PSD"], "channel", freq="1k", bw="500")
    app.add_marker(i["Spectrogram"], "point", freq="1k")
    app.command("next"); app.command("next")
    psd, spg = (app.panels.panes[i[n]] for n in ("PSD", "Spectrogram"))
    for pane in (psd, spg):
        wait_for(app, lambda pane=pane: pane.keep.get("frame") is not None and not pane.dirty)
    assert "RBW" in psd.lbl_readout.cget("text")
    assert psd.tree is not None and psd.tree.winfo_ismapped() and len(psd.tree.get_children()) == 3 # M1, M2 and its PSD row
    assert psd.tree_rows == ["M1", "M2", "M2"]
    assert psd.plotter.ax(0).art("mk0").get_visible() and psd.plotter.ax(0).art("band0").get_visible()
    assert spg.plotter.ax(0).art("vl0").get_visible() and len(spg.tree.get_children()) == 1
    # removing markers hides their artists and the table
    app.del_marker(i["PSD"], "M1"); app.del_marker(i["PSD"], "M2")
    app.command("next")
    wait_for(app, lambda: not psd.dirty and not psd.plotter.ax(0).art("mk0").get_visible() and not psd.tree.winfo_ismapped())
    with pytest.raises(ValueError):
        app.add_marker(i["PSD"], "nope")

def _mouse(pane, kind, f, level=None, button=1):
    """A matplotlib mouse event at frequency f (and level, default mid axis) of the pane's first axis"""
    from matplotlib.backend_bases import MouseEvent
    ax = pane.plotter.ax(0).ax
    y = level if level is not None else sum(ax.get_ylim()) / 2
    x, py = ax.transData.transform((f, y))
    ev = MouseEvent(kind, ax.figure.canvas, x, py, button=button)
    ax.figure.canvas.callbacks.process(kind, ev)

def _gesture(app, pane, f0, f1, level=None):
    _mouse(pane, "button_press_event", f0, level)
    _mouse(pane, "motion_notify_event", (f0 + f1) / 2, level)
    _mouse(pane, "motion_notify_event", f1, level)
    _mouse(pane, "button_release_event", f1, level)
    app.command("next")
    wait_for(app, lambda: pane.drag is None and not pane.dirty)

def test_markers_are_drawn_moved_and_resized_with_the_mouse(app):
    pid = ids(app)["PSD"]
    pane = app.panels.panes[pid]
    app.command("next")
    wait_for(app, lambda: pane.keep.get("frame") is not None and not pane.dirty)
    markers = app.plots.get(pid).markers
    # a drag over empty space draws a channel from the dragged span
    _gesture(app, pane, -3000, -1000)
    (mid, item), = markers.items.items()
    assert item["kind"] == "channel"
    assert abs(float(item["params"]["freq"]) + 2000) < 100 and abs(float(item["params"]["bw"]) - 2000) < 100
    band = pane.keep["frame"].axes[0].bands[0]
    # its right edge widens it, its body moves it
    _gesture(app, pane, band.hi, band.hi + 1000)
    assert abs(float(markers.items[mid]["params"]["bw"]) - 3000) < 100
    _gesture(app, pane, -2000, 0)
    assert abs(float(markers.items[mid]["params"]["freq"]) - 500) < 100
    # a drag of a few pixels draws nothing, a click with the point tool adds a point
    n = len(markers)
    _gesture(app, pane, 3000, 3001)
    assert len(markers) == n
    pane.keep["tool"] = "point"
    _gesture(app, pane, 3000, 3000)
    assert [it["kind"] for it in markers.items.values()] == ["channel", "point"]
    # the point marker moves along frequency
    pt = list(markers.items)[-1]
    m = next(m for m in pane.keep["frame"].axes[0].markers if m.owner == pt)
    lo, hi = sorted(pane.plotter.ax(0).ax.get_ylim())
    _gesture(app, pane, m.x, 4000, level=min(max(m.y, lo + 0.5), hi)) # off the range it is drawn on the edge
    assert abs(float(markers.items[pt]["params"]["freq"]) - 4000) < 100
    # nothing to draw with "off"
    pane.keep["tool"] = "off"
    _gesture(app, pane, -4500, -4000)
    assert len(markers) == 2

def test_the_scope_trigger_level_is_dragged_along_y(app):
    add(app, "Scope")
    pid = ids(app)["Scope"]
    pane = app.panels.panes[pid]
    app.command("next")
    wait_for(app, lambda: pane.keep.get("frame") is not None and not pane.dirty and pane.plotter is not None)
    ax = pane.keep["frame"].axes[0]
    assert ax.xfmt == "time" and any(m.kind == "hline" for m in ax.markers)
    t = (ax.xmin + ax.xmax) / 2
    _mouse(pane, "motion_notify_event", t, 0.0)
    assert str(pane.canvas_widget.cget("cursor")) == "sb_v_double_arrow"
    assert "t " in pane.plotter.ax(0).art("hov_t").get_text() and "s\n" in pane.plotter.ax(0).art("hov_t").get_text()
    _mouse(pane, "button_press_event", t, 0.0)
    _mouse(pane, "motion_notify_event", t, 0.25)
    _mouse(pane, "motion_notify_event", t, 0.5)
    _mouse(pane, "button_release_event", t, 0.5)
    assert app.plots.get(pid).trig_level == pytest.approx(0.5, abs=0.02)
    assert float(pane.vars["trig_level"].get()) == pytest.approx(0.5, abs=0.02) # the settings panel follows
    app.command("next")
    wait_for(app, lambda: pane.drag is None and not pane.dirty)

def test_clicking_a_found_signal_selects_it(app):
    from pyspecan.plots.settings import HAVE_RPPS
    if not HAVE_RPPS:
        pytest.skip("needs rpps (pyspecan[dsp])")
    pid = ids(app)["PSD"]
    pane = app.panels.panes[pid]
    app.add_marker(pid, "signals")
    app.command("next")
    wait_for(app, lambda: pane.keep.get("frame") is not None and not pane.dirty
             and any(b.edit and not b.owner for b in pane.keep["frame"].axes[0].bands))
    box = next(b for b in pane.keep["frame"].axes[0].bands if b.edit and not b.owner)
    centre = (box.lo + box.hi) / 2
    level = (box.ylo + box.yhi) / 2
    _mouse(pane, "button_press_event", centre, level)
    _mouse(pane, "button_release_event", centre, level) # a click: nothing moved
    assert abs(float(app.plots.globals["dsp_freq"]) - centre) < 1.0
    assert app.global_vars["dsp_freq"].get() == app.plots.globals["dsp_freq"] # the sidebar follows
    app.command("next")
    wait_for(app, lambda: pane.drag is None and not pane.dirty)

def test_hover_readout_follows_the_pointer(app):
    pid = ids(app)["PSD"]
    pane = app.panels.panes[pid]
    app.command("next")
    wait_for(app, lambda: pane.keep.get("frame") is not None and not pane.dirty)
    _mouse(pane, "motion_notify_event", 1000)
    text = pane.plotter.ax(0).art("hov_t")
    first = text.get_text().split("\n")[0] # "f 998.4 Hz": the pointer's frequency, to within a pixel or two
    value, unit = first.split()[1:3]
    hz = float(value) * {"Hz": 1, "kHz": 1e3}[unit]
    assert text.get_visible() and abs(hz - 1000) < 30 and "trace" in text.get_text(), text.get_text()
    assert str(pane.canvas_widget.cget("cursor")) == "crosshair"
    from matplotlib.backend_bases import LocationEvent
    canvas = pane.plotter.ax(0).ax.figure.canvas
    canvas.callbacks.process("figure_leave_event", LocationEvent("figure_leave_event", canvas, 0, 0))
    assert not text.get_visible()

def _find(widget, cls):
    """Every descendant widget of a class, depth first"""
    out = []
    for child in widget.winfo_children():
        if isinstance(child, cls):
            out.append(child)
        out += _find(child, cls)
    return out

def test_settings_sections_link_and_globals(app):
    from tkinter import ttk
    psd = ids(app)["PSD"]
    spg = app.panels.add("Spectrogram")
    settle(app)
    pane = app.panels.panes[spg]
    sections = [b.cget("text") for b in _find(pane.pane.settings, ttk.Button)]
    assert "▾ Level" in sections and "▾ Processing" in sections and "▸ Advanced" not in sections # spectrogram has no advanced
    picker = next(c for c in _find(pane.pane.settings, ttk.Combobox) if "none" in c.cget("values"))
    picker.set(next(v for v in picker.cget("values") if v.startswith(psd)))
    picker.event_generate("<<ComboboxSelected>>")
    settle(app)
    assert app.plots.get(psd).link is app.plots.get(spg).link is not None
    pane = app.panels.panes[spg] # settings were rebuilt
    pane.vars["ref_level"].set("-25")
    pane.commit("ref_level")
    assert app.plots.get(psd).ref_level == -25 and app.panels.panes[psd].vars["ref_level"].get() == "-25.0"
    app.global_vars["cal_db"].set("4")
    app.apply_setting("cal_db", "4")
    assert app.plots.get(psd).cal_db == 4 == app.plots.get(spg).cal_db

def test_save_and_load_layout_buttons(app, tmp_path, monkeypatch):
    from pyspecan.utils import dialog
    app.panels.add("Spectrogram")
    path = tmp_path / "saved.json"
    monkeypatch.setattr(dialog, "save_file", lambda *a, **k: path)
    app.view.tb_btn_layout_save.invoke()
    assert '"Spectrogram"' in path.read_text()

    path.write_text('{"rows": [[{"type": "Scope"}, {"type": "PSD", "settings": {"vbw": 2}}]]}')
    monkeypatch.setattr(dialog, "get_file", lambda *a, **k: path)
    app.view.tb_btn_layout_load.invoke()
    settle(app)
    assert layout(app) == [["Scope", "PSD"]] and set(app.panels.panes) == set(app.plots.plots)
    assert app.plots.get(ids(app)["PSD"]).vbw == 2.0

    path.write_text('{"rows": [[{"type": "PSD", "settings": {"vbw": -1}}]]}')
    app.view.tb_btn_layout_load.invoke()
    settle(app)
    assert layout(app) == [["Scope", "PSD"]] # a bad file changes nothing, the toolbar says why
    assert "not loaded" in app.view.tb_lbl_msg.cget("text")

def test_ctrl_c_quits(app):
    import os
    import signal
    os.kill(os.getpid(), signal.SIGINT) # the handler only schedules the quit on tk's loop
    end = time.monotonic() + 5
    while app.running and time.monotonic() < end:
        try:
            app.view.root.update()
        except tk.TclError: # destroyed by the quit
            break
        time.sleep(0.01)
    assert not app.running

def test_export_writes_files(app, tmp_path):
    pid = ids(app)["PSD"]
    pane = app.panels.panes[pid]
    app.command("next")
    wait_for(app, lambda: pane.keep.get("frame") is not None and not pane.dirty)
    pane.export("csv", str(tmp_path / "psd.csv"))
    pane.export("png", str(tmp_path / "psd.png"))
    assert (tmp_path / "psd.csv").read_text().startswith("axis,label,trace,x,y")
    assert (tmp_path / "psd.png").read_bytes()[:4] == b"\x89PNG"
    pane.export("table", str(tmp_path / "t.csv")) # no markers: says so, writes nothing
    assert not (tmp_path / "t.csv").exists()
