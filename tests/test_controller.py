"""Controller core, model block sizing and the console renderer, against a real file sink"""
import numpy as np
import pytest

from pyspecan.config import Sink
from pyspecan.model.model import GetModel
from pyspecan.plots.frame import Axis, Frame, Image, Trace
from pyspecan.controller.base import Controller
from pyspecan.view.CUI.draw import draw_frame

FS = 10_000

@pytest.fixture
def capture(tmp_path):
    """A cf64 capture of two tones, 1 second"""
    t = np.arange(FS) / FS
    sig = (np.exp(2j*np.pi*1000*t) + 0.5*np.exp(-2j*np.pi*2500*t)).astype(np.complex64) # what pysdrlib calls cf64
    path = tmp_path / "capture.cf64"
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
    kw = dict(path=str(capture), fmt="cf64", Fs=str(FS), nfft=256, **kwargs)
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
def test_every_sample_is_framed_exactly_once(capture):
    """Reading the whole file block by block gives the same frames as framing it in one go"""
    c = make(capture)
    c.setting("nfft_exp", 8)
    swept = c.add_plot("Spectrogram")
    c.set_plot(swept, "max_count", 4096)
    c.add_plot("Persistence")                      # realtime psd, runs on the same block
    c.plots.get(swept).set("vbw", 0)
    rows = 0
    while c.step():
        rows += c.ticks[-1][0][swept].axes[0].image.data.shape[0]
    assert rows == FS // 256                       # back to back frames over every sample
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
    assert c.plot_types == ["PSD", "FFT", "IQ", "PMF"]
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
    kw = dict(fmt="cf64", Fs=str(FS), nfft=256)
    c = Recorder(GetModel(Sink.FILE)(**kw), **kw)       # started without -f
    with pytest.raises(ValueError):
        c.command("start")                               # nothing to play yet
    c.setting("path", str(capture))
    c.add_plot("PSD")
    c.command("next")
    assert c.ticks and c.sink.cur_samp == c.model.get_block_size()

    other = tmp_path / "other.cf64"                      # switching files reopens
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
