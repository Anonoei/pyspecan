import json

import numpy as np
import pytest

from pyspecan.obj import Frequency
from pyspecan.plots import PLOTS, PlotSet, Scroller, Source, available
from pyspecan.plots.frame import Image
from pyspecan.plots.freq import to_psd
from pyspecan.plots.source import Stream
from pyspecan.utils.psd import psd as ref_psd
from pyspecan.utils.vbw import vbw, vbw_rows

class FakeModel:
    """The parts of Model plots read"""
    def __init__(self, fs=1000.0, nfft=64, overlap=0.5):
        self.fs, self.nfft, self.overlap = fs, nfft, overlap
        self.samples = np.zeros(0, dtype=np.complex64)
    def get_fs(self): return Frequency.get(self.fs)
    def get_cf(self): return Frequency.get(0)
    def get_nfft(self): return self.nfft
    def get_overlap(self): return self.overlap

def tone(n, f=0.1, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    return (np.exp(2j*np.pi*f*t) + 0.05*(rng.standard_normal(n) + 1j*rng.standard_normal(n))).astype(np.complex64)

def feed(source, model, block):
    model.samples = block
    source.tick()

# --- streams --- #
@pytest.mark.parametrize("hop", [64, 25])
def test_stream_frames_do_not_depend_on_block_boundaries(hop):
    sig = tone(1000)
    nfft = 64
    whole = Stream(nfft, hop, "blackman").frames(sig, 0)
    assert len(whole) == (1000 - nfft)//hop + 1

    stream = Stream(nfft, hop, "blackman")
    parts, i, seq = [], 0, 0
    for size in (7, 130, 63, 200, 1, 99, 500):
        parts.append(stream.frames(sig[i:i+size], seq))
        i, seq = i + size, seq + 1
    parts.append(stream.frames(sig[i:], seq))
    got = np.concatenate([p for p in parts if len(p)])
    np.testing.assert_allclose(got, whole, atol=1e-4)

def test_stream_gap_drops_carry():
    stream = Stream(8, 8, "rect")
    stream.frames(np.ones(12, np.complex64), 0)       # 4 samples carried
    out = stream.frames(np.ones(8, np.complex64), 5)  # missed blocks
    assert len(out) == 1 and not stream.carry.size

def test_stream_caches_per_tick():
    stream = Stream(8, 8, "rect")
    a = stream.frames(np.ones(16, np.complex64), 0)
    assert stream.frames(np.ones(16, np.complex64), 0) is a

def test_source_shares_streams_between_plots():
    model = FakeModel()
    src = Source(model)
    feed(src, model, tone(512))
    assert src.spectra("swept", "blackman") is src.spectra("swept", "blackman")
    assert src.spectra("swept", "blackman").shape == (8, 64)
    assert src.spectra("rt", "blackman").shape == ((512 - 64)//32 + 1, 64)

# --- psd --- #
def test_to_psd_matches_reference():
    model = FakeModel()
    src = Source(model)
    sig = tone(64)
    feed(src, model, sig)
    got = to_psd(src.spectra("swept", "blackman"), model.fs)[0]
    np.testing.assert_allclose(got, ref_psd(sig, model.fs, None, "blackman"), atol=1e-3)

@pytest.mark.parametrize("smooth", [0.5, 3, 10, 40])
def test_vbw_rows_matches_vbw(smooth):
    rng = np.random.default_rng(1)
    data = rng.standard_normal((5, 200)) * 10 - 60
    got = vbw_rows(data, smooth)
    for row, g in zip(data, got):
        np.testing.assert_allclose(g, vbw(row, smooth), atol=1e-6)

# --- settings --- #
def test_settings_validate():
    psd = PLOTS.get("PSD")(Source(FakeModel()))
    psd.set("scale_div", "5")
    assert psd.scale_div == 5.0
    with pytest.raises(ValueError):
        psd.set("scale_div", "0")
    with pytest.raises(ValueError):
        psd.set("window", "nope")
    with pytest.raises(ValueError):
        psd.set("bogus", 1)
    psd.set("ref_level", "auto")
    assert psd.ref_level == "auto"
    psd.set("ref_level", "-30")
    assert psd.ref_level == -30.0
    psd.set("enabled", False)
    assert psd.update() is None

def test_bad_launch_value_falls_back_to_default():
    psd = PLOTS.get("PSD")(Source(FakeModel()), window="nope", vbw="3")
    assert psd.window == "blackman" and psd.vbw == 3.0

def test_setting_reset_flag():
    model = FakeModel()
    src = Source(model)
    psd = PLOTS.get("PSD")(src, vbw=0)
    feed(src, model, tone(256))
    psd.update()
    assert psd._max is not None
    psd.set("vbw", 5) # reset=True
    assert psd._max is None

# --- plots --- #
@pytest.mark.parametrize("name", PLOTS.names())
def test_every_plot_renders_json(name):
    model = FakeModel(nfft=64)
    src = Source(model)
    plot = PLOTS.get(name)(src, x=64, y=32)
    for i in range(3):
        feed(src, model, tone(400, seed=i))
        frame = plot.update()
        assert frame is not None and frame.axes
        assert frame.features() <= PLOTS.get(name).FEATURES
        json.dumps(frame.to_dict())
    plot.reset()

def test_plots_wait_for_a_full_frame():
    model = FakeModel(nfft=64)
    src = Source(model)
    psd = PLOTS.get("PSD")(src)
    feed(src, model, tone(30))
    assert psd.update() is None
    feed(src, model, tone(40)) # 70 samples with the carry
    assert psd.update() is not None

def test_swept_and_rt_plots_run_together():
    model = FakeModel(nfft=64)
    src = Source(model)
    plots = PlotSet(src)
    a, b = plots.add("PSD"), plots.add("Persistence")
    feed(src, model, tone(512))
    frames = plots.update()
    assert set(frames) == {a, b}
    assert len(frames[a].axes[0].traces[0].y) == 64

def test_spectrogram_swept_adds_a_row_per_frame_rt_one():
    model = FakeModel(nfft=64)
    src = Source(model)
    swept = PLOTS.get("Spectrogram")(src)
    rt = PLOTS.get("RT Spectrogram")(src)
    feed(src, model, tone(64*5))
    assert swept.update().axes[0].image.data.shape == (5, 64)
    assert rt.update().axes[0].image.data.shape == (1, 64)

def test_hold_sees_every_frame():
    model = FakeModel(nfft=64)
    src = Source(model)
    psd = PLOTS.get("PSD")(src, vbw=0, ref_level=0)
    loud = tone(64)
    quiet = tone(64) * 0.01
    feed(src, model, np.concatenate((loud, quiet, quiet))) # loud frame is not the one displayed
    frame = psd.update()
    shown = frame.axes[0].traces[-1].y
    held = frame.axes[0].traces[0].y
    assert held.max() > shown.max() + 20

def test_available_filters_by_features():
    assert "IQ 3D" not in available({"line", "scatter", "image"})
    assert "IQ 3D" in available({"line", "scatter", "image", "3d"})
    assert available(set()) == []

# --- scroller --- #
def test_scroller_newest_on_top():
    sc = Scroller()
    one = lambda v, n=1: Image(np.full((n, 3), v, np.uint8), scroll=True, rows=4)
    sc.apply(one(1))
    sc.apply(one(2))
    buf = sc.apply(Image(np.array([[3]*3, [4]*3], np.uint8), scroll=True, rows=4))
    assert buf[:, 0].tolist() == [4, 3, 2, 1]
    buf = sc.apply(Image(np.full((9, 3), 7, np.uint8), scroll=True, rows=4))
    assert buf[:, 0].tolist() == [7, 7, 7, 7]
    buf = sc.apply(Image(np.full((1, 3), 9, np.uint8), scroll=True, rows=4, clear=True))
    assert buf[:, 0].tolist() == [9, 0, 0, 0]

# --- layout --- #
def _plotset(n):
    plots = PlotSet(Source(FakeModel()))
    ids = [plots.add("PSD") for _ in range(n)]
    return plots, ids

def test_move_beside_and_between_rows():
    plots, (a, b, c) = _plotset(3)
    assert plots.layout == [[a], [b], [c]]
    plots.move(c, a, "right")
    assert plots.layout == [[a, c], [b]]
    plots.move(b, a, "left")
    assert plots.layout == [[b, a, c]]            # the emptied row is gone
    plots.move(a, c, "below")
    assert plots.layout == [[b, c], [a]]
    plots.move(a, b, "above")
    assert plots.layout == [[a], [b, c]]
    plots.move(a, None, "end")
    assert plots.layout == [[b, c], [a]]

def test_move_noops_and_errors():
    plots, (a, b) = _plotset(2)
    plots.move(a, a, "left")
    assert plots.layout == [[a], [b]]
    for bad in (("zz", a, "left"), (a, "zz", "left"), (a, b, "diagonal")):
        with pytest.raises(ValueError):
            plots.move(*bad)
    assert plots.layout == [[a], [b]]
    plots.remove(a)
    assert plots.layout == [[b]]

def test_there_is_no_mode_setting_realtime_views_are_their_own_plots():
    for name in PLOTS.names():
        assert "mode" not in [s.key for s in PLOTS.get(name).SETTINGS], name
    assert {"PSD", "Persistence", "Spectrogram", "RT Spectrogram"} <= set(PLOTS.names())

def test_psd_is_the_last_swept_frame():
    model = FakeModel(nfft=64)
    src = Source(model)
    psd = PLOTS.get("PSD")(src)
    feed(src, model, tone(64*3))
    frame = psd.update()
    from pyspecan.utils.vbw import vbw_rows
    swept = to_psd(src.spectra("swept", psd.window), model.fs)
    np.testing.assert_allclose(frame.axes[0].traces[-1].y, vbw_rows(swept, psd.vbw)[-1], atol=1e-6)
