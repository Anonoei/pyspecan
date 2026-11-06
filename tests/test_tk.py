"""tkGUI: adding plots from the dropdown and rearranging them by dragging. Needs a display (xvfb-run)."""
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
    ctrl.view.tb_var_add.set(name)
    ctrl.view.tb_cb_add.event_generate("<<ComboboxSelected>>") # the real binding
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

def test_the_dropdown_offers_the_plots_and_adds_one(app):
    assert list(app.view.tb_cb_add.cget("values")) == app.plot_types
    assert layout(app) == [["PSD"]]
    add(app, "Spectrogram")
    assert layout(app) == [["PSD"], ["Spectrogram"]]
    assert app.view.tb_var_add.get().startswith("+")   # back to the label, ready for the next one
    add(app, "not a plot")
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
