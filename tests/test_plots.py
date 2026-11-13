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
    # the reference divides by N*fs, to_psd by fs*sum(w^2): the window power correction
    w = np.blackman(64)
    corr = 10*np.log10(64 / np.sum(w**2))
    np.testing.assert_allclose(got, ref_psd(sig, model.fs, None, "blackman") + corr, atol=1e-3)

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

def test_spectrogram_adds_one_row_per_refresh():
    model = FakeModel(nfft=64)
    src = Source(model)
    swept = PLOTS.get("Spectrogram")(src)
    rt = PLOTS.get("RT Spectrogram")(src)
    feed(src, model, tone(64*5))
    assert swept.update().axes[0].image.data.shape == (1, 64) # the last frame, as the PSD shows
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

def test_frame_markers_bands_readout_round_trip():
    import json
    from pyspecan.plots.frame import Axis, Band, Frame, Marker
    ax = Axis(yfmt="log10", markers=[Marker(1.5, -20.0, "M1"), Marker(2.0, kind="vline")], bands=[Band(1.0, 2.0, label="ch")])
    d = json.loads(json.dumps(Frame([ax], readout=[("Power", "-3.2 dBm")]).to_dict()))
    assert d["readout"] == [["Power", "-3.2 dBm"]]
    a = d["axes"][0]
    assert a["yfmt"] == "log10" and a["markers"][0]["label"] == "M1" and a["markers"][1]["kind"] == "vline"
    assert a["bands"][0]["lo"] == 1.0 and a["bands"][0]["label"] == "ch"
    assert Frame([Axis()]).to_dict()["readout"] == [] and Frame([Axis()]).features() == set()

# --- measurement plots --- #
def _two_tones(n, nfft=1024, fs=1000.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    x = 0.5*np.exp(2j*np.pi*(100.0/fs)*t) + 0.1*np.exp(2j*np.pi*(-200.0/fs)*t)
    return (x + 0.001*(rng.standard_normal(n) + 1j*rng.standard_normal(n))).astype(np.complex64)

def _readout(frame):
    return dict(frame.readout)

def _table(frame):
    """{marker id: [cells of its rows...]} of a frame's marker table"""
    out, cur = {}, None
    for r in frame.table.rows:
        cur = r.id or cur
        out.setdefault(cur, []).append(r.cells)
    return out

def test_psd_unit_dbfs_reads_tone_amplitude_and_rbw():
    model = FakeModel(nfft=1024)
    src = Source(model)
    psd = PLOTS.get("PSD")(src, unit="dBFS", window="flattop", vbw=0, points=0)
    psd.markers.add("peak", rank=1)
    psd.markers.add("peak", rank=2)
    feed(src, model, _two_tones(4096))
    f = psd.update()
    assert f.axes[0].traces[-1].y.max() == pytest.approx(20*np.log10(0.5), abs=0.1)
    assert [m.label for m in f.axes[0].markers] == ["M1", "M2"]
    assert f.axes[0].markers[0].x == pytest.approx(100.0, abs=1.0)
    assert f.axes[0].markers[1].x == pytest.approx(-200.0, abs=1.0)
    assert _readout(f)["RBW"].endswith("Hz")
    t = _table(f)
    assert f.table.columns[:3] == ["", "Type", "Freq"] and t["M1"][0][:2] == ["M1", "peak"] and "dBFS" in t["M1"][0][3]

def test_no_markers_no_table():
    model = FakeModel(nfft=1024)
    src = Source(model)
    psd = PLOTS.get("PSD")(src)
    feed(src, model, _two_tones(4096))
    assert psd.update().table is None

def test_marker_set_add_edit_remove():
    psd = PLOTS.get("PSD")(Source(FakeModel()))
    a = psd.markers.add("point", freq="1.2k")
    assert a == "M1" and psd.markers.add("channel") == "M2"
    psd.markers.set("m1", "freq", "-300")
    assert psd.markers.items["M1"]["params"]["freq"] == "-300"
    for bad in (("point", {"nope": 1}), ("nope", {})):
        with pytest.raises(ValueError):
            psd.markers.add(bad[0], **bad[1])
    with pytest.raises(ValueError):
        psd.markers.set("M1", "freq", "abc")
    with pytest.raises(ValueError):
        psd.markers.set("M1", "bw", "1k")
    psd.markers.remove("M1")
    assert [m["id"] for m in psd.markers.describe()] == ["M2"]
    assert psd.markers.add("point") == "M3" # ids are not reused
    d = psd.markers.describe()[0]
    assert d["kind"] == "channel" and {f["key"] for f in d["fields"]} == {"freq", "bw"}
    assert not PLOTS.get("FFT")(Source(FakeModel())).MARKERS

def test_delta_fixed_and_per_hz():
    model = FakeModel(nfft=1024)
    src = Source(model)
    psd = PLOTS.get("PSD")(src, unit="dBFS", vbw=0, points=0)
    psd.markers.add("peak")
    psd.markers.add("delta", freq="-200", ref="M1")
    psd.markers.add("point", freq="100", noise=True)
    psd.markers.add("delta", ref="M9")
    feed(src, model, _two_tones(4096))
    t = _table(psd.update())
    assert t["M2"][0][3].startswith("-") and t["M2"][0][3].endswith("dB") and t["M2"][0][2].startswith("-")
    assert "dBFS/Hz" in t["M3"][0][3]
    assert "no marker M9" in t["M4"][0][3]

def test_peak_marker_without_enough_peaks():
    model = FakeModel(nfft=1024)
    src = Source(model)
    psd = PLOTS.get("PSD")(src, vbw=0)
    psd.markers.add("peak", rank=3, excursion=60)
    feed(src, model, _two_tones(4096))
    f = psd.update()
    assert _table(f)["M1"][0][3] == "no peak" and f.axes[0].markers == []

def test_average_and_detector_points():
    model = FakeModel(nfft=1024)
    src = Source(model)
    psd = PLOTS.get("PSD")(src, avg="power", avg_count=4, points=101, detector="peak")
    feed(src, model, _two_tones(4096))
    f = psd.update()
    assert len(f.axes[0].traces[-1].y) == 101
    assert _readout(f)["Avg"].startswith("4/4")
    assert len(psd.last) == 1024
    psd.set("avg_count", 8)
    assert psd._avg.n == 0

def test_channel_marker_matches_tone_power():
    model = FakeModel(nfft=1024)
    src = Source(model)
    plot = PLOTS.get("PSD")(src, unit="dBFS", window="flattop", vbw=0)
    plot.markers.add("channel", freq="100", bw="50")
    feed(src, model, _two_tones(4096))
    f = plot.update()
    rows = _table(f)["M1"]
    assert float(rows[0][3].split()[0]) == pytest.approx(20*np.log10(0.5), abs=0.3)
    assert rows[1][3].endswith("dBFS/Hz") and rows[1][0] == ""
    assert [(b.lo, b.hi) for b in f.axes[0].bands] == [(75.0, 125.0)]

def test_acpr_and_obw_markers():
    model = FakeModel(nfft=1024)
    src = Source(model)
    plot = PLOTS.get("PSD")(src, unit="dBFS", window="flattop", vbw=0)
    plot.markers.add("acpr", freq="100", bw="50", offsets="300, 700")
    plot.markers.add("obw", freq="100", span="200")
    feed(src, model, _two_tones(4096))
    f = plot.update()
    acpr = {r[2]: r[3] for r in _table(f)["M1"][1:]}
    assert float(acpr["-300 Hz"].split()[0]) == pytest.approx(20*np.log10(0.1/0.5), abs=0.5) # the -200 Hz tone
    assert float(acpr["+300 Hz"].split()[0]) < -40 # 400 Hz: only noise
    assert acpr["+700 Hz"] == "outside span" and acpr["-700 Hz"] == "outside span"
    assert len([b for b in f.axes[0].bands if b.label.startswith(("+", "-", "M1"))]) == 3 # main + the two that fit
    assert _table(f)["M2"][0][2] == "99%"
    assert any("centroid" in r[2] for r in _table(f)["M2"]) and any(r[2] == "total" for r in _table(f)["M2"])
    json.dumps(f.to_dict())

def test_markers_on_the_spectrograms():
    model = FakeModel(nfft=256)
    src = Source(model)
    for name in ("Spectrogram", "RT Spectrogram", "Persistence"):
        plot = PLOTS.get(name)(src, unit="dBFS", x=64, y=32)
        plot.markers.add("peak")
        plot.markers.add("channel", freq="100", bw="100")
        feed(src, model, _two_tones(2048))
        f = plot.update()
        ax = f.axes[0]
        assert ax.image is not None and [m.kind for m in ax.markers] == ["vline", "vline"] and ax.bands, name
        assert abs(ax.markers[0].x - 100.0) < 15, name
        assert set(_table(f)) == {"M1", "M2"}
        json.dumps(f.to_dict())

def test_ccdf_plot():
    model = FakeModel(nfft=64)
    src = Source(model)
    plot = PLOTS.get("CCDF")(src)
    rng = np.random.default_rng(0)
    for _ in range(5):
        feed(src, model, ((rng.standard_normal(20000) + 1j*rng.standard_normal(20000))/np.sqrt(2)).astype(np.complex64))
        f = plot.update()
    assert f.axes[0].yfmt == "log10" and {t.name for t in f.axes[0].traces} == {"gauss", "ccdf"}
    assert float(_readout(f)["1%"].split()[0]) == pytest.approx(6.6, abs=0.4)
    plot.set("bins", 500)
    assert plot.ccdf.total == 0

def test_power_vs_time_history():
    model = FakeModel(nfft=64)
    src = Source(model)
    plot = PLOTS.get("Power vs Time")(src, unit="dBFS", history=10, pvt_freq="100", pvt_bw="200")
    for i in range(3):
        feed(src, model, tone(400, f=0.1, seed=i))
        f = plot.update()
    y = f.axes[0].traces[0].y
    assert len(y) == 10
    assert f.axes[0].traces[0].x[-1] == 0
    assert _readout(f)["Peak"].endswith("dBFS")

def test_markers_read_the_unsmoothed_trace():
    model = FakeModel(nfft=1024)
    src = Source(model)
    psd = PLOTS.get("PSD")(src, unit="dBFS", window="flattop") # default vbw smooths the drawn line
    psd.markers.add("peak")
    feed(src, model, _two_tones(4096))
    f = psd.update()
    assert float(_table(f)["M1"][0][3].split()[0]) == pytest.approx(20*np.log10(0.5), abs=0.2)
    assert f.axes[0].traces[-1].y.max() < f.axes[0].markers[0].y - 3 # the drawn line is smoothed

def test_markers_outside_the_span_say_so_instead_of_reading_the_floor():
    """After retuning, a marker placed for another frequency range has nothing to measure"""
    model = FakeModel(nfft=256)
    src = Source(model)
    psd = PLOTS.get("PSD")(src, unit="dBFS", vbw=0)
    for kind, params in (("point", {"freq": "100k"}), ("delta", {"freq": "100k"}), ("channel", {"freq": "100k", "bw": "10k"}),
                         ("acpr", {"freq": "100k", "bw": "10k"}), ("obw", {"freq": "100k", "span": "10k"})):
        psd.markers.add(kind, **params) # the span is +-500 Hz
    psd.markers.add("channel", freq="0", bw="200")  # one inside, still measured
    feed(src, model, _two_tones(2048))
    f = psd.update()
    t = _table(f)
    for mid in ("M1", "M2", "M3", "M4", "M5"):
        assert t[mid][0][3] == "outside span", (mid, t[mid])
    assert "outside span" not in t["M6"][0][3] and float(t["M6"][0][3].split()[0]) > -100
    assert [b.owner for b in f.axes[0].bands] == ["M6"] and f.axes[0].markers == [m for m in f.axes[0].markers if m.owner == ""]
    json.dumps(f.to_dict())
