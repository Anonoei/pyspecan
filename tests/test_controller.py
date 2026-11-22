"""Controller core, model block sizing and the console renderer, against a real file sink"""
import json

import numpy as np
import pytest

from pyspecan.config import Sink
from pyspecan.controller.base import Controller
from pyspecan.model.model import GetModel
from pyspecan.plots.frame import Axis, Frame, Image, Trace
from pyspecan.view.CUI.draw import draw_frame

FS = 10_000

@pytest.fixture
def capture(tmp_path):
    """A cf32 capture of two tones, 1 second"""
    t = np.arange(FS) / FS
    sig = (np.exp(2j*np.pi*1000*t) + 0.5*np.exp(-2j*np.pi*2500*t)).astype(np.complex64) # what pysdrlib calls cf32
    path = tmp_path / "capture.cf32"
    sig.tofile(path)
    return path

class Recorder(Controller):
    """A controller that keeps what it was asked to show"""
    def __init__(self, model, **kwargs):
        super().__init__(model, None, **kwargs)
        self.ticks = []
    def deliver(self, frames, status):
        self.ticks.append((frames, status))

def make(capture, **kwargs):
    kw = dict(path=str(capture), fmt="cf32", Fs=str(FS), nfft=256, **kwargs)
    return Recorder(GetModel(Sink.FILE)(**kw), **kw)

# --- model --- #
def test_block_size_follows_sweep_time_within_limits(capture):
    m = make(capture).model
    assert m.get_block_size() == 500          # 50 ms of 10 kHz
    m.set_sweep_time(1)                       # asks for 10 samples: at least min_fft frames
    hop = int(256 * (1 - m.get_overlap()))
    assert m.get_block_size() == 256 + 2*hop
    m.set_sweep_time(10_000)                  # asks for the whole file: at most max_fft frames / block_max
    assert m.get_block_size() == min(256 + 511*hop, 1024*1024)
    assert m.get_sweep_time() == pytest.approx(m.get_block_size() / FS * 1000)

def test_changing_settings_does_not_rewind_the_file(capture):
    c = make(capture)
    c.command("next")
    pos = c.sink.cur_samp
    assert pos > 0
    c.setting("nfft_exp", 9)
    c.setting("overlap", 0.5)
    c.setting("sweep", 80)
    assert c.sink.cur_samp == pos

def test_model_validation(capture):
    m = make(capture).model
    with pytest.raises(ValueError):
        m.set_overlap(1.0)
    with pytest.raises(ValueError):
        m.set_nfft(2)

# --- playback --- #
def test_spectrogram_adds_one_row_per_refresh(capture):
    """Each refresh adds exactly one spectrogram row, however many frames the block holds"""
    c = make(capture)
    c.setting("nfft_exp", 8)
    swept = c.add_plot("Spectrogram")
    c.set_plot(swept, "max_count", 4096)
    c.add_plot("Persistence")                      # realtime psd, runs on the same block
    c.plots.get(swept).set("vbw", 0)
    ticks = 0
    while c.step():
        assert c.ticks[-1][0][swept].axes[0].image.data.shape[0] == 1
        ticks += 1
    assert ticks > 0
    assert c.message == "" and c.step() is False   # then the end of the file

def test_commands_and_errors(capture):
    c = make(capture)
    with pytest.raises(ValueError):
        c.command("bogus")
    with pytest.raises(ValueError):
        c.setting("nfft_exp", 99)
    with pytest.raises(ValueError):
        c.setting("fs", "not a rate")
    with pytest.raises(ValueError):
        c.setting("path", "/nonexistent")
    c.command("start")
    assert c.playing
    c.command("stop")
    c.command("next"); c.command("next")
    block = c.model.get_block_size()
    assert c.sink.cur_samp == 2 * block
    c.command("prev")
    assert c.sink.cur_samp == block
    c.command("reset")
    assert c.sink.cur_samp == 0

def test_prev_does_not_stitch_carried_samples(capture):
    c = make(capture)
    c.add_plot("Persistence")
    c.step(); c.step()
    assert c.step(forward=False)  # jumps back, the stream starts over instead of joining unrelated samples
    assert all(not s.carry.size or s.seen == c.source.seq for s in c.source._streams.values())

def test_tick_paces_and_stops_at_the_end(capture):
    c = make(capture, show=0)
    c.setting("show", 0)
    c.command("start")
    n = 0
    while c.tick():
        n += 1
    assert n == FS // c.model.get_block_size()
    assert not c.playing and c.message == "END"

def test_plot_types_follow_the_views_features(capture):
    c = make(capture)
    c.FEATURES = {"line"}
    from pyspecan.plots.settings import HAVE_RPPS
    dsp = ["Analog Demod", "Error Vector", "Error Vector Spectrum", "Network Analyzer", "Impulse Response"] if HAVE_RPPS else [] # on rpps
    assert c.plot_types == ["PSD", "FFT", "IQ", "PMF", "Scope", "Frequency vs Time", "CCDF", "Power vs Time", "Occupancy",
                            "Phase Noise", *dsp] # no Sweep: a file is no radio
    with pytest.raises(ValueError):
        c.add_plot("Spectrogram")

def test_state_is_json_serializable(capture):
    import json
    c = make(capture)
    c.add_plot("PSD")
    json.dumps(c.get_state())

# --- console renderer --- #
def _frames():
    x = np.linspace(-1, 1, 500)
    yield Frame([Axis(xmin=-5e3, xmax=5e3, xfmt="freq", ymin=-100, ymax=0, traces=[Trace(np.sin(x*9)*50-50)])], "line")
    yield Frame([Axis(traces=[Trace(np.sin(x*30), x)])], "xy autorange")
    yield Frame([Axis(xmin=-1, xmax=1, ymin=-1, ymax=1, square=True, traces=[Trace(x, x, kind="scatter")])], "scatter")
    yield Frame([Axis(xmin=0, xmax=1, image=Image(np.arange(5000, dtype=np.uint8).reshape(50, 100), "magma"))], "image")
    yield Frame([Axis(xmin=0, xmax=1, ymin=-100, ymax=0, offscale="above", image=Image(np.zeros((8, 8), np.uint8), "hot")),
                 Axis(traces=[Trace(np.full(3, np.nan))])], "two axes")

@pytest.mark.parametrize("color", [True, False])
@pytest.mark.parametrize("size", [(100, 30), (20, 6), (200, 12)])
def test_draw_frame_fits_its_box(color, size):
    import re
    width, height = size
    for frame in _frames():
        images = [ax.image.data if ax.image else None for ax in frame.axes]
        lines = draw_frame(frame, images, width, height, color)
        assert lines and len(lines) <= height + len(frame.axes)
        for line in lines:
            visible = re.sub(r"\x1b\[[0-9;]*m", "", line)
            assert len(visible) <= width, (frame.title, len(visible), width)

# --- opening files after launch (the browser / file dialog flow) ---
def test_file_chosen_after_launch_plays(capture, tmp_path):
    kw = dict(fmt="cf32", Fs=str(FS), nfft=256)
    c = Recorder(GetModel(Sink.FILE)(**kw), **kw)       # started without -f
    with pytest.raises(ValueError):
        c.command("start")                               # nothing to play yet
    c.setting("path", str(capture))
    c.add_plot("PSD")
    c.command("next")
    assert c.ticks and c.sink.cur_samp == c.model.get_block_size()

    other = tmp_path / "other.cf32"                      # switching files reopens
    np.zeros(2000, np.complex64).tofile(other)
    c.setting("path", str(other))
    assert c.sink.cur_samp == 0 and c.sink.max_samp == 2000
    c.command("next")
    assert c.sink.cur_samp == c.model.get_block_size()

def test_playback_failures_say_why(capture, capsys):
    c = make(capture)
    c.sink.dev.next = lambda count: (_ for _ in ()).throw(RuntimeError("disk on fire"))
    c.command("start")
    assert c.tick() is False
    assert "disk on fire" in c.message and "disk on fire" in capsys.readouterr().err

def test_draw_frame_shows_markers_bands_and_readout():
    import re

    from pyspecan.plots.frame import Band, Marker
    x = np.linspace(-1, 1, 400)
    ax = Axis(xmin=-5e3, xmax=5e3, xfmt="freq", ymin=-100, ymax=0, traces=[Trace(np.sin(x*9)*50-50)],
              markers=[Marker(1e3, -20.0, "M1"), Marker(-2e3, kind="vline")], bands=[Band(2e3, 3e3, label="ch")])
    from pyspecan.plots.frame import Table, TableRow
    table = Table(["", "Type", "Freq", "Result"], [TableRow("M1", ["M1", "peak", "1 kHz", "-20 dBFS"]), TableRow("", ["", "", "x", "-30 dBFS/Hz"])])
    frame = Frame([ax], "t", readout=[("RBW", "1.7 kHz")], table=table)
    lines = ["".join(re.sub(r"\x1b\[[0-9;]*m", "", l)) for l in draw_frame(frame, [None], 80, 24, True)]
    text = "\n".join(lines)
    assert "▼M1" in text and "ch" in text and "RBW: 1.7 kHz" in text and "M1  peak  1 kHz  -20 dBFS" in text and "-30 dBFS/Hz" in text
    assert len(lines) <= 24 + 1 and all(len(l) <= 80 for l in lines)
    ccdf = Frame([Axis(ymin=-6, ymax=0, yfmt="log10", traces=[Trace(np.linspace(-6, 0, 20))])])
    assert "1e-3" in "\n".join(draw_frame(ccdf, [None], 60, 20, False))

def test_draw_frame_shows_marks_on_images():
    import re

    from pyspecan.plots.frame import Band, Image, Marker
    data = np.full((20, 100), 128, dtype=np.uint8)
    spg = Axis(xmin=-5e3, xmax=5e3, xfmt="freq", image=Image(data),
               markers=[Marker(-3e3, kind="vline", label="M2")], bands=[Band(1e3, 3e3, label="ch")])
    for color in (False, True):
        lines = [re.sub(r"\x1b\[[0-9;]*m", "", l) for l in draw_frame(Frame([spg]), [data], 60, 12, color)]
        body = lines[:-1]
        assert all(l.count("│") >= 4 for l in body[1:-1]) # the axis bar, two band edges and the marker
        assert "M2" in body[0] and "ch" in body[-1]
        assert all(len(l) <= 60 for l in lines)
    pst = Axis(xmin=-5e3, xmax=5e3, xfmt="freq", ymin=-100, ymax=0, image=Image(data), markers=[Marker(0.0, -50.0, "M1")])
    text = "\n".join(draw_frame(Frame([pst]), [data], 60, 12, False))
    assert "▼M1" in text

def test_draw_frame_shows_level_lines_boxes_and_time():
    import re

    from pyspecan.plots.frame import Band, Image, Marker
    strip = lambda ls: [re.sub(r"\x1b\[[0-9;]*m", "", l) for l in ls]
    ax = Axis(xmin=-1e-3, xmax=1e-3, xfmt="time", ymin=-1, ymax=1, traces=[Trace(np.zeros(50))],
              markers=[Marker(0.0, 0.5, "T", kind="hline")], bands=[Band(-5e-4, 5e-4, ylo=-0.5, yhi=0.0)])
    lines = strip(draw_frame(Frame([ax]), [None], 60, 20, True))
    assert "ms" in lines[-1] and "-1 ms" in lines[-1] # ticks in the unit of the span
    assert any(l.rstrip().endswith("T") for l in lines) # the level's label at the right edge
    data = np.full((20, 100), 128, dtype=np.uint8)
    pst = Axis(xmin=-5e3, xmax=5e3, xfmt="freq", ymin=-100, ymax=0, image=Image(data),
               markers=[Marker(0.0, -50.0, "thr", kind="hline")], bands=[Band(-2e3, 2e3, ylo=-80.0, yhi=-20.0)])
    text = "\n".join(strip(draw_frame(Frame([pst]), [data], 60, 14, False)))
    assert "╌" in text and "thr" in text and "─" in text # level line, its label, the box's top / bottom
    spg = Axis(xmin=-5e3, xmax=5e3, xfmt="freq", image=Image(data), markers=[Marker(0.0, -50.0, "thr", kind="hline")])
    assert "thr" not in "\n".join(draw_frame(Frame([spg]), [data], 60, 14, False)) # no levels to draw it at

def test_trace_points_are_one_per_bin():
    from pyspecan.view.CUI.draw import _trace_x
    ax = Axis(xmin=0.0, xmax=100.0)
    np.testing.assert_allclose(_trace_x(Trace(np.zeros(4)), ax), [0, 25, 50, 75]) # as markers place bins, as tk draws them
    np.testing.assert_allclose(_trace_x(Trace(np.zeros(3)), Axis()), [0, 1, 2])

# --- markers edited by the mouse --- #
def test_marker_edits_redraw_the_current_block_while_stopped(capture):
    c = make(capture)
    pid = c.add_plot("PSD")
    c.command("next")
    n = len(c.ticks)
    mid = c.add_marker(pid, "channel", freq="1000", bw="500")
    assert len(c.ticks) == n + 1 and c.ticks[-1][0][pid].axes[0].bands[0].edit == ("freq", "bw")
    c.set_marker_params(pid, mid, {"freq": "2500.0", "bw": "800.0"})
    band = c.ticks[-1][0][pid].axes[0].bands[0]
    assert (band.lo, band.hi, band.owner) == (2100.0, 2900.0, mid)
    c.del_marker(pid, mid)
    assert len(c.ticks) == n + 3 and c.ticks[-1][0][pid].table is None
    c.playing = True # while playing the next block shows it
    pt = c.add_marker(pid, "point")
    c.set_marker(pid, pt, "freq", "1000")
    assert len(c.ticks) == n + 3
    with pytest.raises(ValueError):
        c.set_marker_params(pid, "M1", {"freq": "1k", "nope": 1}) # nothing applied

def test_marker_set_many_is_all_or_nothing():
    from tests.test_plots import FakeModel

    from pyspecan.plots import PLOTS, Source
    psd = PLOTS.get("PSD")(Source(FakeModel()))
    mid = psd.markers.add("channel", freq="100", bw="50")
    psd.markers.set_many(mid, {"freq": "200.5", "bw": "10"})
    assert psd.markers.items[mid]["params"] == {"freq": "200.5", "bw": "10"}
    for bad in ({"freq": "300", "bw": "abc"}, {"freq": "300", "nope": "1"}):
        with pytest.raises(ValueError):
            psd.markers.set_many(mid, bad)
        assert psd.markers.items[mid]["params"] == {"freq": "200.5", "bw": "10"}

def test_frames_say_which_markers_the_mouse_can_edit():
    import json

    from tests.test_plots import FakeModel, _two_tones, feed

    from pyspecan.plots import PLOTS, Source
    model = FakeModel(nfft=256)
    src = Source(model)
    for name in ("PSD", "Spectrogram"):
        plot = PLOTS.get(name)(src, vbw=0)
        for kind, params in (("point", {"freq": "100"}), ("peak", {}), ("channel", {"freq": "100", "bw": "50"}), ("obw", {"freq": "100", "span": "200"})):
            plot.markers.add(kind, **params)
        feed(src, model, _two_tones(2048))
        d = json.loads(json.dumps(plot.update().to_dict()))["axes"][0]
        by_owner = {m["owner"]: m for m in d["markers"] if m["owner"]}
        assert set(by_owner) == {"M1", "M2"} and by_owner["M1"]["edit"] == by_owner["M2"]["edit"] == "freq", name # point and (static) peak, the others are bands
        edits = {b["owner"]: b["edit"] for b in d["bands"] if b["edit"]}
        assert edits == {"M3": ["freq", "bw"], "M4": ["freq", "span"]}, name

def test_sample_rate_must_be_positive(capture):
    c = make(capture)
    for bad in ("0", "-1k", "0.0", "nan", "inf"):
        with pytest.raises(ValueError):
            c.setting("fs", bad)
        assert c.sink.get_fs().raw == FS and c.get_state()["fs"] # the rate and the state sent to a connecting client are untouched
    c.setting("fs", "20k")
    assert c.sink.get_fs().raw == 20_000
    with pytest.raises(ValueError):
        GetModel(Sink.FILE)(path=str(capture), fmt="cf32", Fs="0") # and a bad launch value fails up front instead of at the first client

def test_plot_settings_redraw_the_current_block_while_stopped(capture):
    c = make(capture)
    pid = c.add_plot("PSD")
    c.command("next")
    n = len(c.ticks)
    c.set_plot(pid, "unit", "dBFS")
    assert len(c.ticks) == n + 1 # the plot shows the new unit without waiting for another block
    c.set_plot(pid, "enabled", False)
    assert len(c.ticks) == n + 1
    c.playing = True
    c.set_plot(pid, "ref_level", "-10")
    assert len(c.ticks) == n + 1 # playing: the next block shows it

def test_a_client_gone_mid_send_is_dropped_quietly():
    import asyncio
    import logging
    pytest.importorskip("fastapi")
    from pyspecan.controller.WEB.websocket import WebSocketManager
    class Gone:
        async def accept(self): pass
        async def send_json(self, msg): raise RuntimeError("Cannot call send once a close message has been sent")
    class Parent:
        log = logging.getLogger("test")
    ws = WebSocketManager(Parent())
    async def run():
        cid = await ws.connect(Gone())
        assert await ws.send(cid, {"type": "state"}) is False and cid not in ws.connections
        assert await ws.send(cid, {"type": "error"}) is False # already dropped: no KeyError
    asyncio.run(run())

def test_draw_frame_log_x_axis():
    import re
    ax = Axis(xmin=10.0, xmax=1e5, xlog=True, xfmt="freq", ymin=-100, ymax=0,
              traces=[Trace(np.linspace(-20, -80, 50), np.geomspace(10, 1e5, 50))])
    lines = [re.sub(r"\x1b\[[0-9;]*m", "", l) for l in draw_frame(Frame([ax]), [None], 60, 12, False)]
    assert lines[-1].split()[0] == "10" and lines[-1].split()[-1] == "100k" and "1k" in lines[-1] # 10 .. 1k .. 100k evenly

def test_marker_actions_through_the_controller_and_console(capture):
    from pyspecan.controller.CUI.base import Controller as Console
    class Both(Recorder): # the console's marker command on a recording controller
        cmd_marker = Console.cmd_marker
        _need = Console._need
    kw = dict(path=str(capture), fmt="cf32", Fs=str(FS), nfft=256)
    c = Both(GetModel(Sink.FILE)(**kw), **kw)
    pid = c.plots.layout[0][0]
    mid = c.add_marker(pid, "peak")
    with pytest.raises(ValueError, match="no trace yet"):
        c.marker_action(pid, mid, "next")
    c.command("next")
    before = c.plots.get(pid).markers.items[mid]["params"]["freq"]
    c.cmd_marker([pid, "act", mid, "next"]) # the console's "marker <id> act <marker> next"
    assert c.plots.get(pid).markers.items[mid]["params"]["freq"] != before
    with pytest.raises(ValueError, match="no action"):
        c.marker_action(pid, mid, "sideways")

def test_plot_actions_through_the_controller_and_console(capture):
    from pyspecan.controller.CUI.base import Controller as Console
    class Both(Recorder):
        cmd_act = Console.cmd_act
        _need = Console._need
    kw = dict(path=str(capture), fmt="cf32", Fs=str(FS), nfft=256)
    c = Both(GetModel(Sink.FILE)(**kw), **kw)
    pid = c.plots.layout[0][0]
    assert c.get_state()["plots"][pid]["actions"] == ["store ref", "clear ref"]
    c.command("next")
    c.cmd_act([pid, "store", "ref"]) # the console's "act p1 store ref"
    assert c.plots.get(pid).ref is not None
    with pytest.raises(ValueError, match="no action"):
        c.plot_action(pid, "sideways")


def test_state_groups_the_plot_types(capture):
    c = make(capture)
    s = c.get_state()
    assert set(s["plot_info"]) == set(s["plot_types"]) and s["categories"][0] == "Spectrum"
    groups = c.plot_groups()
    assert [n for _, names in groups for n in names] == [n for cat, _ in groups for n in s["plot_types"]
                                                         if s["plot_info"][n]["category"] == cat] # by category, in order
    assert sorted(n for _, names in groups for n in names) == sorted(s["plot_types"]) # each once

def test_export_through_the_controller_and_console(capture, tmp_path):
    from pyspecan.controller.CUI.base import Controller as Console
    class Both(Recorder):
        cmd_export = Console.cmd_export
        _need = Console._need
    kw = dict(path=str(capture), fmt="cf32", Fs=str(FS), nfft=256)
    c = Both(GetModel(Sink.FILE)(**kw), **kw)
    pid = c.plots.layout[0][0]
    with pytest.raises(ValueError, match="drawn nothing yet"):
        c.export(pid, "csv")
    c.command("next")
    assert c.export(pid, "csv").startswith("axis,label,trace,x,y")
    with pytest.raises(ValueError, match="no table"):
        c.export(pid, "table") # no markers
    with pytest.raises(ValueError, match="one of"):
        c.export(pid, "xls")
    out = tmp_path / "psd.json"
    c.cmd_export([pid, "json", str(out)]) # the console's "export p1 json psd.json"
    assert json.loads(out.read_text())["axes"]
    c.del_plot(pid)
    c.add_plot("Scope")
    c.command("next")
    assert pid not in c.latest # a removed plot's frame is let go
