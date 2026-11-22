import json

import numpy as np
import pytest

from pyspecan.obj import Frequency
from pyspecan.plots import PLOTS, PlotSet, Scroller, Source, available
from pyspecan.plots.frame import Image
from pyspecan.plots.freq import to_psd
from pyspecan.plots.settings import HAVE_RPPS
from pyspecan.plots.source import Stream
from pyspecan.utils.vbw import vbw, vbw_rows


def ref_psd(samples, Fs=1.0, vbw=None, win="blackman"):
    """Straightforward windowed periodogram in dB/Hz, what the plots are checked against"""
    from pyspecan.measure.windows import WindowLUT
    from pyspecan.utils.vbw import vbw as _vbw
    n = len(samples)
    out = np.fft.fftshift(10.0*np.log10(np.abs(np.fft.fft(samples * WindowLUT[win](n)))**2 / (n*Fs)))
    return out if vbw is None else _vbw(out, vbw)

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
    for row, g in zip(data, got, strict=True):
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

def test_bad_initial_value_raises():
    assert PLOTS.get("PSD")(Source(FakeModel()), vbw="3").vbw == 3.0
    with pytest.raises(ValueError, match="Window"):
        PLOTS.get("PSD")(Source(FakeModel()), window="nope")

def test_setting_reset_flag():
    model = FakeModel()
    src = Source(model)
    psd = PLOTS.get("PSD")(src, vbw=0)
    feed(src, model, tone(256))
    psd.update()
    assert psd.trace_data(1) is not None # trace 2: max hold
    psd.set("vbw", 5) # reset=True
    assert psd.trace_data(1) is None

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
    held = next(t for t in frame.axes[0].traces if t.name == "t2").y # max hold
    assert held.max() > shown.max() + 20

def _psd_traces(**kw):
    model = FakeModel(nfft=64)
    src = Source(model)
    psd = PLOTS.get("PSD")(src, vbw=0, ref_level=0, points=0, **kw)
    def step(scale):
        feed(src, model, tone(64) * scale)
        f = psd.update()
        return {t.name: t for t in f.axes[0].traces}, f
    return psd, step

def test_trace_modes():
    psd, step = _psd_traces(t1_mode="clear/write", t2_mode="max hold", t3_mode="min hold", t4_mode="average", avg_count=2)
    step(1.0)
    tr, f = step(0.01) # 40 dB down
    peak = lambda name: float(tr[name].y.max())
    assert peak("t2") > peak("t1") + 35 and abs(peak("t3") - peak("t1")) < 1 # max keeps the loud one, min follows down
    assert peak("t2") > peak("t4") > peak("t1") # the average of the two
    assert [t.color for t in f.axes[0].traces] == ["#5cb85c", "#5b9bd5", "#d9534f", "#e6d84a"] # 4..1, the marker trace last
    assert _readout(f)["Avg"].startswith("2/2")

def test_view_freezes_blank_hides_and_a_new_mode_starts_over():
    psd, step = _psd_traces(t3_mode="blank")
    step(1.0)
    psd.set("t2_mode", "view") # keeps the hold it had
    tr, _ = step(0.01)
    assert "t3" not in tr and float(tr["t2"].y.max()) > float(tr["t1"].y.max()) + 35
    psd.set("t2_mode", "max hold") # starts over
    tr, _ = step(0.01)
    assert abs(float(tr["t2"].y.max()) - float(tr["t1"].y.max())) < 1

def test_markers_read_the_marker_trace():
    psd, step = _psd_traces(marker_trace="2")
    step(1.0)
    tr, f = step(0.01)
    assert np.array_equal(psd.last, psd.trace_data(1)) and f.axes[0].traces[-1].name == "t2"
    psd.set("t2_mode", "blank")
    psd.set("marker_trace", "2")
    _, f = step(0.01)
    assert psd.last is not None # blank keeps what it had: markers still read it, it is just not drawn
    assert all(t.name != "t2" for t in f.axes[0].traces)

def test_settings_from_before_traces_still_load():
    from pyspecan.plots import layout
    psd = PLOTS.get("PSD")(Source(FakeModel()), show_max=False, show_min=True, avg="log")
    assert (psd.t1_mode, psd.t2_mode, psd.t3_mode, psd.avg) == ("average", "blank", "min hold", "log")
    assert PLOTS.get("PSD")(Source(FakeModel()), avg="off").t1_mode == "clear/write"
    spec = layout.parse_inline(["PSD show_max=off avg=power"])
    layout.validate(spec)
    assert spec.rows[0][0].settings == {"t2_mode": "blank", "avg": "power", "t1_mode": "average"}

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
    psd = PLOTS.get("PSD")(src, t1_mode="average", avg="power", avg_count=4, points=101, detector="peak")
    feed(src, model, _two_tones(4096))
    f = psd.update()
    assert len(f.axes[0].traces[-1].y) == 101
    assert _readout(f)["Avg"].startswith("4/4")
    assert len(psd.last) == 1024
    psd.set("avg_count", 8)
    assert psd._traces[0].avg is None # starts over

def test_reduced_traces_sit_on_the_bin_frequencies():
    """The detector's groups are drawn at the frequency of their center, so markers (at bin frequencies) sit on the line"""
    model = FakeModel(nfft=64)
    src = Source(model)
    psd = PLOTS.get("PSD")(src, points=10, detector="peak", vbw=0, t2_mode="blank", t3_mode="blank")
    psd.markers.add("peak")
    feed(src, model, _two_tones(4096, nfft=64))
    ax = psd.update().axes[0]
    t = ax.traces[-1]
    freqs = psd.bin_freqs(64)
    edges = np.linspace(0, 64, 11).astype(int)
    np.testing.assert_allclose(t.x, freqs[0] + (edges[:-1] + edges[1:] - 1) / 2 * (1000.0 / 64))
    peak = next(m for m in ax.markers if m.label == "M1")
    k = int(np.argmax(t.y))
    assert abs(t.x[k] - peak.x) <= (edges[k + 1] - edges[k]) / 2 * (1000.0 / 64) # within its own group
    full = PLOTS.get("PSD")(src, points=0)
    feed(src, model, _two_tones(4096, nfft=64))
    assert full.update().axes[0].traces[-1].x is None # one point per bin: spaced by the axis

def test_peak_threshold_is_a_level_line_to_drag():
    model = FakeModel(nfft=256)
    src = Source(model)
    psd, spg = PLOTS.get("PSD")(src), PLOTS.get("Spectrogram")(src)
    for p in (psd, spg):
        p.markers.add("peak", threshold="-40")
        p.markers.add("peak")
    feed(src, model, _two_tones(4096, nfft=256))
    lines = [m for m in psd.update().axes[0].markers if m.kind == "hline"]
    assert [(m.y, m.owner, m.edit) for m in lines] == [(-40.0, "M1", "threshold")] # only the marker with a threshold
    assert not any(m.kind == "hline" for m in spg.update().axes[0].markers) # no levels on a spectrogram

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

# --- persistence --- #
def _pst_run(blocks, **kw):
    model = FakeModel(nfft=64, overlap=0.5)
    src = Source(model)
    p = PLOTS.get("Persistence")(src, **{"x": 0, "y": 100, "ref_level": 0, "scale_div": 10, **kw})
    frames = []
    for block in blocks:
        feed(src, model, block)
        frames.append(p.render().axes[0])
    return frames

def test_persistence_traces_live_and_max_hold():
    sig = tone(2000)
    quiet = (sig * 1e-4).astype(np.complex64)
    first, second = _pst_run([sig, quiet], show_live=True, show_max=True)
    live = {t.name: t for t in second.traces}
    assert set(live) == {"max", "live"}
    assert len(live["live"].y) == 64 == second.image.data.shape[1]
    assert (live["max"].y >= live["live"].y).all()
    assert live["max"].y.max() > live["live"].y.max() + 20 # the tone is still held after it is gone
    assert live["max"].alpha < 1
    assert _pst_run([sig])[0].traces == [] # off by default

def test_persistence_signal_goes_dark_at_once_and_leaves_a_ghost():
    sig = tone(2000)
    quiet = (sig * 1e-4).astype(np.complex64)
    a, b = _pst_run([sig, quiet], ghost=0.0)
    ga, gb = _pst_run([sig, quiet], ghost=0.4)
    old = (a.image.data > 0) & (b.image.data == 0)       # lit by the first block only
    assert old.any()
    assert (b.image.data[old] == 0).all()                # no ghost: dark at once
    assert (gb.image.data[old] > 0).all()                # ghost: still there
    assert (gb.image.data[old] <= ga.image.data[old] * 0.4 + 1).all() # dimmer than it was
    live = b.image.data > 0
    assert (gb.image.data[live] == b.image.data[live]).all() # what is lit now is not dimmed

def test_persistence_ghost_fades_with_ghost_time():
    sig = tone(2000)
    quiet = (sig * 1e-4).astype(np.complex64)
    a, b = _pst_run([sig, quiet], ghost=0.0)
    old = (a.image.data > 0) & (b.image.data == 0)
    kept = _pst_run([sig, quiet], persistence=0.0)[1].image.data
    gone = _pst_run([sig, quiet], persistence=1e-4)[1].image.data
    assert (kept[old] > 0).all() and (gone[old] == 0).all()

def test_persistence_style_and_width():
    sig = tone(2000)
    vec, = _pst_run([sig], style="vector", x=128)
    dot, = _pst_run([sig], style="dot", x=128)
    assert vec.image.data.shape[1] == dot.image.data.shape[1] == 128
    assert (vec.image.data > 0).sum() >= (dot.image.data > 0).sum()

def test_persistence_scale_does_not_flicker():
    sig = tone(2000)
    f = _pst_run([sig, sig, sig], persistence=5.0)
    assert f[0].image.data.max() == 255 and f[2].image.data.max() == 255
    assert f[2].image.data.dtype == np.uint8

# --- scope --- #
def clean(n, f=1/50, start=0):
    return np.exp(2j*np.pi*f*np.arange(start, start + n)).astype(np.complex64)

def _trace(frame, name):
    return next(t for t in frame.axes[0].traces if t.name == name)

def test_scope_trigger_locks_phase_across_ticks():
    model = FakeModel(fs=1000.0, nfft=64)
    src = Source(model)
    scope = PLOTS.get("Scope")(src, overlay=1)
    grid = np.linspace(-5e-3, 50e-3, 40) # seconds, inside the 64 sample screen
    seen = []
    for i in range(4):
        feed(src, model, clean(400, start=400*i + 7*i)) # blocks need not hold whole periods
        frame = scope.update()
        t = _trace(frame, "i0")
        assert dict(frame.readout)["Trig"] == "triggered"
        assert abs(np.interp(0.0, t.x, t.y)) < 1e-3       # crosses the level at x = 0
        assert np.interp(1e-3, t.x, t.y) > 0               # rising
        seen.append(np.interp(grid, t.x, t.y))
    for s in seen[1:]:
        np.testing.assert_allclose(s, seen[0], atol=1e-3)

def test_scope_axis_is_in_seconds_with_a_trigger_level_line():
    model = FakeModel(fs=1000.0, nfft=64)
    src = Source(model)
    scope = PLOTS.get("Scope")(src, overlay=1, trig_level=0.25, trig_pos=10.0)
    feed(src, model, clean(400))
    ax = scope.update().axes[0]
    assert ax.xfmt == "time" and ax.xlabel == "Time"
    assert ax.xmin == pytest.approx(-6 / 1000) and ax.xmax == pytest.approx(58 / 1000) # 64 samples, 10% before
    level = next(m for m in ax.markers if m.kind == "hline")
    assert (level.y, level.owner, level.edit) == (0.25, "", "trig_level") # dragged, it sets the plot's trigger level
    phase = PLOTS.get("Scope")(src, overlay=1, channel="Phase")
    feed(src, model, clean(400))
    assert not any(m.kind == "hline" for m in phase.update().axes[0].markers) # the level is not in radians

def test_scope_overlay_draws_older_sweeps_faded():
    model = FakeModel(fs=1000.0, nfft=64)
    src = Source(model)
    scope = PLOTS.get("Scope")(src, overlay=4, channel="I")
    feed(src, model, clean(1000))
    frame = scope.update()
    names = [t.name for t in frame.axes[0].traces]
    assert names == ["i3", "i2", "i1", "i0"] # newest drawn last
    assert _trace(frame, "i0").alpha == 1.0 and _trace(frame, "i3").alpha < 1.0

def test_scope_screen_longer_than_a_block_carries_samples():
    model = FakeModel(fs=1000.0, nfft=64)
    src = Source(model)
    scope = PLOTS.get("Scope")(src, time_div="100m") # 1000 samples a screen, blocks are 400
    feed(src, model, clean(400))
    assert dict(scope.update().readout)["Trig"] == "filling"
    for i in range(1, 4):
        feed(src, model, clean(400, start=400*i))
        frame = scope.update()
    assert len(_trace(frame, "i0").y) == 1000
    src.reset() # the position jumped: the carry is gone
    feed(src, model, clean(400))
    assert dict(scope.update().readout)["Trig"] == "filling"

def test_scope_normal_holds_and_single_freezes():
    model = FakeModel(fs=1000.0, nfft=64)
    src = Source(model)
    scope = PLOTS.get("Scope")(src, trig_mode="normal")
    feed(src, model, clean(400))
    first = scope.update()
    feed(src, model, np.full(400, 0.5+0j, np.complex64)) # no crossing
    held = scope.update()
    assert dict(held.readout)["Trig"] == "armed"
    assert held.axes is first.axes

    scope.set("trig_mode", "single")
    feed(src, model, clean(400))
    shot = scope.update()
    assert dict(shot.readout)["Trig"] == "stopped"
    feed(src, model, clean(400, start=123))
    assert scope.update() is shot
    scope.set("trig_level", 0.2) # re-arms
    feed(src, model, clean(400))
    assert scope.update() is not shot

def test_scope_auto_free_runs_without_trigger():
    model = FakeModel(fs=1000.0, nfft=64)
    src = Source(model)
    scope = PLOTS.get("Scope")(src)
    feed(src, model, np.full(400, 0.5+0j, np.complex64))
    frame = scope.update()
    assert dict(frame.readout)["Trig"] == "auto" and len(_trace(frame, "i0").y) == 64

def test_scope_roll_envelope_is_continuous_across_ticks():
    model = FakeModel(fs=1000.0, nfft=64)
    src = Source(model)
    scope = PLOTS.get("Scope")(src, trig_mode="roll", channel="I", time_div="500m") # 5000 samples, 10 per column
    for i in range(10):
        feed(src, model, np.arange(400*i, 400*(i+1)).astype(np.complex64))
        frame = scope.update()
    y = _trace(frame, "i").y
    mins, maxs = y[0::2], y[1::2]
    assert len(mins) == 400
    np.testing.assert_array_equal(np.diff(mins), 10)
    np.testing.assert_array_equal(maxs - mins, 9)
    assert frame.axes[0].xmax == 0.0 and _trace(frame, "i").x[-1] <= 0.0

def test_scope_roll_fine_timebase_draws_samples():
    model = FakeModel(fs=1000.0, nfft=64)
    src = Source(model)
    scope = PLOTS.get("Scope")(src, trig_mode="roll")
    feed(src, model, clean(400))
    t = _trace(scope.update(), "i")
    assert len(t.y) == 64 and t.x[-1] == 0.0

def test_scope_time_parsing():
    from pyspecan.plots.settings import parse_time
    assert parse_time("10u") == pytest.approx(1e-5)
    assert parse_time("2ms") == pytest.approx(2e-3)
    assert parse_time("auto") == 0.0 and parse_time("") == 0.0
    scope = PLOTS.get("Scope")(Source(FakeModel()))
    with pytest.raises(ValueError):
        scope.set("time_div", "fast")

def test_scope_roll_block_longer_than_the_screen():
    model = FakeModel(fs=1000.0, nfft=64)
    src = Source(model)
    scope = PLOTS.get("Scope")(src, trig_mode="roll", channel="I", time_div="500m") # 500 columns of 10 samples
    feed(src, model, np.arange(7003).astype(np.complex64))       # 700 columns, 3 samples left over
    scope.update()
    feed(src, model, np.arange(7003, 7210).astype(np.complex64)) # completes 21 more
    y = _trace(scope.update(), "i").y
    mins = y[0::2]
    assert len(mins) == 500 and mins[-1] == 7200
    np.testing.assert_array_equal(np.diff(mins), 10)

# --- settings hierarchy and links --- #
def _linked(*names, **kw):
    model = FakeModel(nfft=1024)
    src = Source(model)
    plots = PlotSet(src, globals=kw)
    ids = [plots.add(n) for n in names]
    return model, src, plots, ids

def test_fields_carry_group_scope_and_advanced():
    psd = PLOTS.get("PSD")(Source(FakeModel()))
    fields = {f["key"]: f for f in psd.fields()}
    assert fields["ref_level"]["group"] == "Level" and fields["ref_level"]["scope"] == "link"
    assert fields["avg"]["scope"] == "plot" and fields["detector"]["advanced"]
    assert "cal_db" not in fields # global now
    assert all("group" in f for name, cls in PLOTS.items() for f in cls(Source(FakeModel())).fields())

def test_link_shares_link_settings_only():
    _, _, plots, (a, b) = _linked("PSD", "Spectrogram")
    plots.set(b, "vbw", 3)
    lid = plots.link(a, b)
    assert plots.get(a).vbw == 3 and plots.get(a).link is plots.get(b).link
    for key, value in (("ref_level", "-20"), ("scale_div", 5), ("window", "hanning"), ("unit", "dBFS")):
        plots.set(a, key, value)
        assert getattr(plots.get(b), key) == getattr(plots.get(a), key)
    plots.set(a, "t2_mode", "blank") # plot scope stays per plot
    assert plots.get(a).t2_mode == "blank"
    d = plots.describe()
    assert d["links"] == {lid: [b, a]} and d["plots"][a]["link"] == lid
    assert b in d["plots"][a]["linkable"]

def test_link_change_resets_every_member():
    model, src, plots, (a, b) = _linked("PSD", "Spectrogram")
    plots.link(a, b)
    feed(src, model, tone(4096))
    plots.update()
    assert plots.get(a).trace_data(1) is not None
    plots.set(b, "window", "hanning") # reset flagged, set on the other plot
    assert plots.get(a).trace_data(1) is None

def test_linked_auto_ref_level_resolves_once():
    model, src, plots, (a, b) = _linked("PSD", "RT Spectrogram")
    plots.link(a, b)
    feed(src, model, tone(4096))
    frames = plots.update()
    link = plots.get(a).link
    assert link.auto is not None
    assert frames[a].axes[0].ymax == link.auto
    assert plots.get(b).resolve_ref(np.array([1000.0])) == link.auto # does not re-resolve
    plots.set(b, "ref_level", "auto")
    assert link.auto is None

def test_unlink_keeps_values_and_splits_markers():
    model, src, plots, (a, b, c) = _linked("PSD", "Spectrogram", "Persistence")
    plots.get(a).markers.add("peak")
    plots.get(b).markers.add("point")
    plots.link(a, b)
    plots.link(c, a) # joins the existing link
    assert plots.get(a).markers is plots.get(b).markers is plots.get(c).markers
    assert sorted(plots.get(a).markers.items) == ["M1", "M2"]
    plots.set(c, "scale_div", 7)
    plots.unlink(c)
    assert plots.get(c).link is None and plots.get(c).scale_div == 7
    assert plots.get(c).markers is not plots.get(a).markers and len(plots.get(c).markers) == 2
    plots.set(c, "scale_div", 3)
    assert plots.get(a).scale_div == 7
    plots.remove(b) # the last member keeps the link's markers
    assert plots.get(a).link is None and not plots.links and len(plots.get(a).markers) == 2

def test_shared_markers_draw_on_every_member():
    model, src, plots, (a, b) = _linked("PSD", "Spectrogram", unit="dBFS", vbw=0)
    plots.link(b, a)
    plots.get(a).markers.add("peak")
    feed(src, model, _two_tones(4096))
    frames = plots.update()
    assert frames[a].table is not None and frames[b].table is not None
    assert frames[b].axes[0].markers[0].kind == "vline"

def test_link_needs_the_same_domain():
    _, _, plots, (a, f, s) = _linked("PSD", "FFT", "Scope")
    for other in (f, s):
        with pytest.raises(ValueError):
            plots.link(a, other)
    with pytest.raises(ValueError):
        plots.link(a, a)
    assert plots.linkable(f) == []

def test_retype_keeps_link_when_it_can():
    _, _, plots, (a, b) = _linked("PSD", "Spectrogram")
    plots.link(a, b)
    plots.retype(a, "Persistence")
    assert plots.get(a).link is plots.get(b).link is not None
    plots.retype(a, "FFT")
    assert plots.get(a).link is None and plots.get(b).link is None

def test_retype_keeps_markers():
    _, _, plots, (a,) = _linked("PSD")
    plots.get(a).markers.add("point", freq="100")
    plots.get(a).markers.add("channel")
    plots.retype(a, "Spectrogram")
    assert list(plots.get(a).markers.items) == ["M1", "M2"]
    assert plots.get(a).markers.add("peak") == "M3"
    plots.retype(a, "FFT")
    assert not plots.get(a).MARKERS

def test_retype_of_a_linked_plot_does_not_duplicate_markers():
    _, _, plots, (a, b) = _linked("PSD", "Spectrogram")
    plots.link(a, b)
    plots.get(a).markers.add("point", freq="100")
    plots.retype(a, "Persistence")
    assert plots.get(a).link is plots.get(b).link
    assert list(plots.get(a).markers.items) == ["M1"]

def test_global_cal_reaches_every_plot():
    model, src, plots, (a, b) = _linked("PSD", "Power vs Time", unit="dBm", cal_db=-10)
    assert plots.globals["cal_db"] == -10 and plots.get(a).cal_db == -10
    plots.set_global("cal_db", 5)
    assert plots.get(a).cal_db == 5 and plots.get(b).cal_db == 5
    plots.set(a, "ext_gain", 3) # a plot's set of a global key also reaches all
    assert plots.get(b).ext_gain == 3
    got = plots.describe()["globals"]["settings"]
    assert {k: got[k] for k in ("cal_db", "ext_gain")} == {"cal_db": 5.0, "ext_gain": 3.0} # (and the DSP globals with rpps)
    with pytest.raises(ValueError):
        plots.set_global("vbw", 1)

def test_cal_db_still_a_cli_flag():
    import argparse

    from pyspecan.plots import args_plots, global_kwargs
    parser = argparse.ArgumentParser()
    args_plots(parser)
    kw = vars(parser.parse_args(["--cal_db", "-7"]))
    assert global_kwargs(kw) == {"cal_db": -7.0}
    with pytest.raises(SystemExit): # per plot settings go in --plot / --layout now
        parser.parse_args(["--vbw", "2"])

# --- extensions --- #
class FakeEntryPoint:
    def __init__(self, name, load):
        self.name, self.value, self._load = name, f"fake:{name}", load
    def load(self):
        return self._load()

@pytest.fixture
def extensions(monkeypatch):
    """Run plots.load_extensions over fake entry points, unregister what they added afterwards"""
    import pyspecan.plots as plots
    from pyspecan.plots.markers import MARKER_KINDS
    before = (set(PLOTS.names()), set(MARKER_KINDS.names()))
    monkeypatch.delenv("PYSPECAN_NO_EXTENSIONS", raising=False)
    def run(*eps):
        monkeypatch.setattr(plots.metadata, "entry_points", lambda group: list(eps) if group == plots.EXTENSION_GROUP else [])
        monkeypatch.setattr(plots, "_extensions_loaded", False)
        return plots.load_extensions()
    yield run
    for name in set(PLOTS.names()) - before[0]:
        PLOTS.unregister(name)
    for name in set(MARKER_KINDS.names()) - before[1]:
        MARKER_KINDS.unregister(name)

def _register_ext():
    from pyspecan.plots import LINE, Frame, MarkerKind, Plot, marker_kind, plot
    @plot("ExtTest")
    class ExtTest(Plot):
        FEATURES = frozenset({LINE})
        def render(self):
            return Frame()
    @marker_kind("ext")
    class Ext(MarkerKind):
        pass

def test_extension_registers_plot_and_marker(extensions):
    from pyspecan.plots import layout
    from pyspecan.plots.markers import MARKER_KINDS
    assert extensions(FakeEntryPoint("ext", _register_ext)) == ["ext"]
    assert PLOTS.names()[-1] == "ExtTest"  # after the built in plots
    assert "ExtTest" in available({"line"}) and "ext" in MARKER_KINDS
    layout.validate(layout.parse_inline(["ext_test"]))

def test_extension_failures_warn_and_continue(extensions, caplog):
    def broken():
        raise ImportError("no module named nope")
    def clash():
        from pyspecan.plots import Plot, plot
        plot("PSD")(type("Clash", (Plot,), {}))
    psd = PLOTS.get("PSD")
    with caplog.at_level("WARNING", logger="pyspecan.plots"):
        loaded = extensions(FakeEntryPoint("a_broken", broken), FakeEntryPoint("b_clash", clash),
                            FakeEntryPoint("c_ok", _register_ext))
    assert loaded == ["c_ok"] and "ExtTest" in PLOTS
    assert PLOTS.get("PSD") is psd
    assert "a_broken" in caplog.text and "b_clash" in caplog.text and "already registered" in caplog.text

def test_extensions_disabled(extensions, monkeypatch):
    monkeypatch.setenv("PYSPECAN_NO_EXTENSIONS", "1")
    assert extensions(FakeEntryPoint("ext", _register_ext)) == [] and "ExtTest" not in PLOTS

def test_missing_extension_hint():
    from pyspecan.plots import layout
    with pytest.raises(ValueError, match="need their package installed"):
        layout.validate(layout.parse_inline(["NotInstalled"]))
    with pytest.raises(ValueError, match="unknown marker kind 'nope'.*need their package installed"):
        layout.validate(layout.parse_inline(["PSD marker=nope"]))

def test_frame_dict_carries_level_lines_box_bands_and_time_axes():
    from pyspecan.plots.frame import Axis, Band, Frame, Marker, Trace, fmt_time
    ax = Axis(xmin=0, xmax=1e-3, xfmt="time", markers=[Marker(0, 0.5, "T", kind="hline", edit="trig_level")],
              bands=[Band(1, 2), Band(1, 2, ylo=-3, yhi=None)])
    d = json.loads(json.dumps(Frame([ax]).to_dict()))["axes"][0]
    assert d["xfmt"] == "time" and d["markers"][0]["kind"] == "hline" and d["markers"][0]["owner"] == ""
    assert (d["bands"][0]["ylo"], d["bands"][0]["yhi"]) == (None, None) and (d["bands"][1]["ylo"], d["bands"][1]["yhi"]) == (-3.0, None)
    scope = Axis(xmin=-1e-5, xmax=1e-5, traces=[Trace(np.zeros(3), np.array([-1e-5, 1.23e-7, 1e-5]))])
    assert Frame([scope]).to_dict()["axes"][0]["traces"][0]["x"][1] == pytest.approx(1.23e-7) # x keeps its precision relative to the span
    assert fmt_time(2.5e-4, 1e-3) == "0.25 ms" and fmt_time(2.5e-4) == "250 µs" and fmt_time(2.0) == "2 s"

# --- mouse drags (plots/drag.py, what tk uses) --- #
def _drag_axis():
    from pyspecan.plots.frame import Axis, Band, Marker
    return Axis(xmin=0, xmax=1000, ymin=-100, ymax=0, traces=[],
                markers=[Marker(100.0, -20.0, "M1", owner="M1", edit="freq"), Marker(900.0, -20.0, "M3", owner="M3")],
                bands=[Band(400.0, 600.0, owner="M2", edit=("freq", "bw")), Band(700.0, 800.0, owner="M4")])

def test_hit_test_finds_markers_edges_and_bodies():
    from pyspecan.plots.drag import hit_test
    ax, px, py = _drag_axis(), (lambda x: x), (lambda y: -y) # 1 px per Hz, 1 px per dB
    m = hit_test(ax, 0, px, 103, 20, py)
    assert (m.mode, m.owner, m.edit) == ("marker", "M1", "freq")
    assert hit_test(ax, 0, px, 103, 80, py) is None # far below the triangle
    assert hit_test(ax, 0, px, 103) is not None     # no levels: only the frequency counts
    assert hit_test(ax, 0, px, 398).mode == "left" and hit_test(ax, 0, px, 604).mode == "right"
    body = hit_test(ax, 0, px, 500)
    assert (body.mode, body.owner, body.edit) == ("move", "M2", ("freq", "bw"))
    assert hit_test(ax, 0, px, 900, 20, py) is None and hit_test(ax, 0, px, 750) is None # not editable
    assert hit_test(ax, 0, px, 300) is None

def test_drag_preview_and_commit():
    from pyspecan.plots.drag import Drag, commit, hit_test, preview
    ax = _drag_axis()
    d = hit_test(ax, 0, lambda x: x, 604)
    d.start = 604
    d.to(700.0, 96)
    shown = preview(ax, d, 0)
    assert (shown.bands[0].lo, shown.bands[0].hi) == (400.0, 700.0) and ax.bands[0].hi == 600.0
    assert preview(ax, d, 1) is ax
    assert commit("off", d, True) == ("set", "M2", {"freq": "550.0", "bw": "300.0"})
    d = hit_test(ax, 0, lambda x: x, 500)
    d.start = 500
    d.to(450.0, -50)
    assert commit("channel", d, True) == ("set", "M2", {"freq": "450.0", "bw": "200.0"})
    d = hit_test(ax, 0, lambda x: x, 100)
    d.start = 100
    d.to(150.0, 50)
    assert preview(ax, d, 0).markers[0].x == 150.0
    assert commit("channel", d, True) == ("set", "M1", {"freq": "150.0"})
    still = hit_test(ax, 0, lambda x: x, 100)
    assert commit("channel", still, False) is None # a plain click on a marker
    new = Drag(0, "new", 200.0, 200.0, start=200.0)
    new.to(300.0, 100)
    assert preview(ax, new, 0).bands[-1].lo == 200.0
    assert commit("channel", new, True) == ("add", "channel", {"freq": "250.0", "bw": "100.0"})
    assert commit("obw", new, True) == ("add", "obw", {"freq": "250.0", "span": "100.0"})
    assert commit("point", new, True) is None and commit("channel", new, False) is None
    assert commit("point", Drag(0, "new", 200.0, 200.0), False) == ("add", "point", {"freq": "200.0"})
    assert commit("off", new, True) is None

def test_level_lines_drag_along_y_and_plot_marks_set_plot_settings():
    from pyspecan.plots.drag import Drag, commit, hit_test, preview, settled
    from pyspecan.plots.frame import Axis, Marker
    ax = Axis(xmin=0, xmax=1000, ymin=-1, ymax=1, markers=[Marker(0.0, kind="vline"), Marker(0.0, 0.2, "T", kind="hline", edit="trig_level"),
                                                         Marker(0.0, -0.5, "M1 thr", kind="hline", owner="M1", edit="threshold")])
    px, level = (lambda x: x), (lambda y: 100 - 100 * y) # 100 px per unit, y up
    assert hit_test(ax, 0, px, 500, 87, None, level) is None and hit_test(ax, 0, px, 500, 70) is None # off the line / no levels
    d = hit_test(ax, 0, px, 500, 78, None, level)
    assert (d.mode, d.owner, d.edit, d.lo) == ("level", "", "trig_level", 0.2)
    d.start = 0.2
    d.to(123.0, -30, 0.5)
    shown = preview(ax, d, 0)
    assert shown.markers[1].y == 0.5 and shown.markers[2].y == -0.5 and ax.markers[1].y == 0.2
    assert settled(shown, d) and not settled(ax, d)
    assert commit("channel", d, False) == ("plot", "", {"trig_level": "0.5"}) # narrow in x, still a drag
    thr = hit_test(ax, 0, px, 10, 151, None, level)
    thr.to(0.0, 20, -0.25)
    assert commit("off", thr, True) == ("set", "M1", {"threshold": "-0.25"})
    still = Drag(0, "level", 0.2, 0.2, "", "trig_level")
    assert commit("off", still, True) is None

def test_bands_with_a_y_span_are_hit_inside_it():
    from pyspecan.plots.drag import hit_test
    from pyspecan.plots.frame import Axis, Band
    ax = Axis(xmin=0, xmax=1000, ymin=-100, ymax=0, bands=[Band(400.0, 600.0, owner="M2", edit=("freq", "bw"), ylo=-60.0, yhi=-20.0),
                                                           Band(700.0, 800.0, owner="M3", edit=("freq", "bw"), ylo=-50.0)])
    px, level = (lambda x: x), (lambda y: -y) # 1 px per dB, pixels grow downwards
    assert hit_test(ax, 0, px, 500, 40, None, level).mode == "move"
    assert hit_test(ax, 0, px, 500, 10, None, level) is None and hit_test(ax, 0, px, 500, 90, None, level) is None
    assert hit_test(ax, 0, px, 500).mode == "move" # no levels: x only
    assert hit_test(ax, 0, px, 750, 90, None, level) is None and hit_test(ax, 0, px, 750, 5, None, level).mode == "move" # up to the top

# --- 3d spectrogram, frequency vs time, occupancy, iq density --- #
def test_3d_spectrogram_keeps_rows_newest_in_front():
    model = FakeModel(nfft=256)
    src = Source(model)
    p = PLOTS.get("3D Spectrogram")(src, max_count=4, points=64)
    p.markers.add("channel", freq="100", bw="50")
    for i in range(6):
        feed(src, model, _two_tones(1024, nfft=256, seed=i))
        f = p.update()
    ax = f.axes[0]
    assert ax.projection == "3d" and (ax.ymin, ax.ymax) == (0, 3) and p.FEATURES == {"line", "3d"}
    assert [t.name for t in ax.traces] == ["r3", "r2", "r1", "r0"] # oldest at the back drawn first
    assert all(len(t.x) == len(t.y) == len(t.z) == 64 and set(t.y) == {float(t.name[1:])} for t in ax.traces)
    assert all(ax.zmin <= t.z.min() and t.z.max() <= ax.zmax for t in ax.traces) # clipped to the level range
    newest = ax.traces[-1]
    assert abs(newest.x[int(np.argmax(newest.z))] - 100) < 1000 / 64 # the strong tone, at its frequency
    assert [(b.lo, b.hi) for b in ax.bands if b.label == "M1"] == [(75.0, 125.0)] and f.table is not None # on the floor
    p.set("framing", "rt")
    feed(src, model, _two_tones(1024, nfft=256))
    assert len(p.update().axes[0].traces) == 1 # a reset

def test_frequency_vs_time_tracks_a_tone_and_fm():
    model = FakeModel(fs=1000.0, nfft=64)
    src = Source(model)
    p = PLOTS.get("Frequency vs Time")(src, count=500)
    feed(src, model, clean(2000, f=0.1)) # 100 Hz
    f = p.update()
    ax = f.axes[0]
    assert ax.xfmt == "time" and ax.yfmt == "freq" and (ax.ymin, ax.ymax) == (-500.0, 500.0)
    np.testing.assert_allclose(ax.traces[0].y, 100.0, atol=1e-3)
    assert dict(f.readout)["Mean"] == "100 Hz"
    t = np.arange(4000) / 1000
    fm = np.exp(2j*np.pi*np.cumsum(50*np.sin(2*np.pi*5*t)) / 1000).astype(np.complex64) # 50 Hz deviation
    p.set("fspan", "200")
    p.set("count", 4000)
    feed(src, model, fm)
    f = p.update()
    assert (f.axes[0].ymin, f.axes[0].ymax) == (-100.0, 100.0)
    assert dict(f.readout)["Deviation"].startswith("50") or dict(f.readout)["Deviation"].startswith("49.9")
    assert len(f.axes[0].traces[0].y) <= 1000 # drawn as an envelope

def test_occupancy_counts_bins_above_the_threshold():
    model = FakeModel(nfft=256)
    src = Source(model)
    p = PLOTS.get("Occupancy")(src, points=0)
    for i in range(3):
        feed(src, model, _two_tones(4096, nfft=256, seed=i))
        f = p.update()
    live, occ = f.axes
    level = live.markers[0]
    assert (level.kind, level.owner, level.edit, level.y) == ("hline", "", "threshold", p.thr) # drag it to set the threshold
    freqs = p.bin_freqs(256)
    pct = occ.traces[0].y
    assert pct[np.argmin(np.abs(freqs - 100))] == 100.0 and pct[np.argmin(np.abs(freqs - 400))] < 10.0 # tone vs noise
    assert dict(f.readout)["Frames"] == str(p.frames) and p.frames > 3
    p.set("threshold", "200") # above everything: nothing is occupied, the counts restart
    feed(src, model, _two_tones(4096, nfft=256))
    f = p.update()
    assert f.axes[1].traces[0].y.max() == 0.0 and f.axes[0].markers[0].y == 200.0

def test_iq_density_puts_symbols_in_their_quadrants():
    model = FakeModel(nfft=64)
    src = Source(model)
    p = PLOTS.get("IQ Density")(src, bins=32, decay=0.0)
    rng = np.random.default_rng(0)
    sym = ((rng.integers(0, 2, 4000) * 2 - 1) + 1j * (rng.integers(0, 2, 4000) * 2 - 1)) / np.sqrt(2)
    feed(src, model, (sym + 0.02 * rng.standard_normal(4000)).astype(np.complex64))
    f = p.update()
    ax = f.axes[0]
    img = ax.image.data
    assert img.shape == (32, 32) and img.dtype == np.uint8 and ax.square and ax.xmin == -ax.xmax
    quads = [img[:16, 16:], img[:16, :16], img[16:, :16], img[16:, 16:]] # +I+Q (top right), -I+Q, -I-Q, +I-Q
    assert all(q.max() > 200 for q in quads) and img.max() == 255
    assert img[14:18, 14:18].max() == 0 # nothing at the origin
    one = np.full(4000, (1 + 1j) / np.sqrt(2), dtype=np.complex64) # only the top right symbol
    feed(src, model, one)
    img = p.update().axes[0].image.data
    assert img[:16, 16:].max() == 255 and img[16:, :16].max() == 0 # decay 0: only the latest block

# --- measurement markers: peak table, harmonics, TOI, limit --- #
def _tones_psd(**markers):
    fs, n = 1000.0, 8192
    t = np.arange(n) / fs
    # tones at 100 / 120 Hz, their third order products at 80 / 140 Hz (-40 dBc), a 200 Hz tone at -30 dBc
    x = (np.exp(2j*np.pi*100*t) + np.exp(2j*np.pi*120*t) + 0.01*(np.exp(2j*np.pi*80*t) + np.exp(2j*np.pi*140*t))
         + 0.0316*np.exp(2j*np.pi*200*t) + 1e-4*np.random.default_rng(0).standard_normal(n)).astype(np.complex64)
    model = FakeModel(fs=fs, nfft=1024)
    src = Source(model)
    p = PLOTS.get("PSD")(src, unit="dBFS", vbw=0, window="flattop")
    for kind, params in markers.items():
        p.markers.add(kind, **params)
    feed(src, model, x)
    return p.update()

def _rows(frame, mid):
    out, cur = {}, None
    for r in frame.table.rows:
        cur = r.id or cur
        if cur == mid:
            out.setdefault(mid, []).append(r.cells[2:])
    return out[mid]

def test_peak_table_lists_the_strongest():
    f = _tones_psd(peaks={"count": 5})
    rows = _rows(f, "M1")
    freqs = sorted(round(float(r[0].split()[1])) for r in rows)
    assert freqs == [80, 100, 120, 140, 200]
    assert len([m for m in f.axes[0].markers if m.label.startswith("M1.")]) == 5

def test_toi_from_two_tones_and_their_products():
    f = _tones_psd(toi={})
    rows = _rows(f, "M1")
    toi = [r for r in rows if r[0] == "TOI"][0][1]
    assert abs(float(toi.split()[0]) - 20.0) < 0.5 # tones at 0 dBFS, IM3 at -40 dBc: 0 + 40 / 2

def test_harmonics_of_a_given_fundamental():
    f = _tones_psd(harmonics={"freq": "100", "count": 3})
    rows = {r[0].split()[0]: r[1] for r in _rows(f, "M1")}
    assert abs(float(rows["H2"].split()[0]) + 30.0) < 0.5 # 200 Hz at -30 dBc
    assert "THD" in rows and float(rows["THD"].split("%")[0]) > 3.0

def test_limit_line_pass_fail_and_drag():
    ok = _tones_psd(limit={"level": -20.0, "freq": "200", "span": "50"})
    assert _rows(ok, "M1")[0][1].startswith("PASS, 10")
    bad = _tones_psd(limit={"level": -35.0, "freq": "200", "span": "50"})
    verdict = _rows(bad, "M1")[0][1]
    assert verdict.startswith("FAIL by") and abs(float(verdict.split()[2]) - 5.0) < 0.2
    line = next(m for m in bad.axes[0].markers if m.kind == "hline")
    assert (line.owner, line.edit, line.y) == ("M1", "level", -35.0) # drag it to move the limit
    low = _tones_psd(limit={"level": -10.0, "side": "lower", "freq": "100", "span": "4"})
    assert _rows(low, "M1")[0][1].startswith("PASS")

# --- phase noise, analog demod --- #
def test_phase_noise_follows_a_random_walk_phase():
    fs, n, sig = 1e6, 65536, 2e-3
    model = FakeModel(fs=fs, nfft=4096)
    src = Source(model)
    p = PLOTS.get("Phase Noise")(src, pn_nfft=16384, avg_count=200)
    rng = np.random.default_rng(0)
    ph = 0.0
    for i in range(8):
        pn = ph + np.cumsum(rng.standard_normal(n)) * sig
        ph = pn[-1]
        t = (np.arange(n) + i * n) / fs
        feed(src, model, np.exp(1j * (2*np.pi*100e3*t + pn)).astype(np.complex64))
        f = p.update()
    ax = f.axes[0]
    assert ax.xlog and ax.xfmt == "freq" and ax.xmin > 0
    for off in (1e3, 1e4, 1e5): # L(f) of a random walk phase: sig^2 / fs / (2 sin(pi f / fs))^2
        theory = 10 * np.log10(sig**2 / fs / (2 * np.sin(np.pi * off / fs))**2)
        assert abs(np.interp(off, ax.traces[0].x, ax.traces[0].y) - theory) < 1.5, off
    r = dict(f.readout)
    assert abs(float(r["Carrier"].split()[0]) - 100) < 0.1 and "° rms" in r["Integrated"]

@pytest.mark.skipif(not HAVE_RPPS, reason="Analog Demod is on rpps (pyspecan[dsp])")
@pytest.mark.parametrize("demod, check", [
    ("FM", lambda r: r["Deviation"].startswith("5") and r["Mod freq"] == "1 kHz" and float(r["SINAD"].split()[0]) > 30),
    ("PM", lambda r: abs(float(r["Deviation"].split()[0]) - 2.0) < 0.1 and r["Mod freq"] == "1 kHz"),
    ("AM", lambda r: r["Mod freq"] == "1 kHz" and r["Depth"] == "50.0%"),
    ("USB", lambda r: abs(float(r["Mod freq"].split()[0]) * {"Hz": 1, "kHz": 1e3}[r["Mod freq"].split()[1]] - 1e3) < 5 and "Power" in r), # coarse: 7.5 kHz audio
])
def test_analog_demod(demod, check):
    fs, n = 1e6, 50000
    t = np.arange(n) / fs
    m = np.sin(2 * np.pi * 1e3 * t)
    if demod == "FM":
        x = np.exp(1j * (2*np.pi*100e3*t + 5e3 / 1e3 * (1 - np.cos(2*np.pi*1e3*t)))) # 5 kHz deviation
    elif demod == "PM":
        x = np.exp(1j * (2*np.pi*100e3*t + 2.0 * m)) # 2 rad
    elif demod == "USB":
        x = np.exp(2j*np.pi*101e3*t) + 1e-6 * np.exp(2j*np.pi*100e3*t) # a 1 kHz tone above a (suppressed) carrier
    else:
        x = (1 + 0.5 * m) * np.exp(2j*np.pi*100e3*t) # 50 %
    model = FakeModel(fs=fs, nfft=4096)
    src = Source(model)
    kw = {"carrier": "100k", "demod_bw": "3k"} if demod == "USB" else {"demod_bw": "50k"}
    p = PLOTS.get("Analog Demod")(src, mode=demod, **kw)
    feed(src, model, x.astype(np.complex64))
    f = p.update()
    r = dict(f.readout)
    assert r["Carrier"] == "100 kHz" and check(r), r
    assert f.axes[0].xfmt == "time" and f.axes[1].xfmt == "freq"

# --- the peak marker: lands on the highest, stays, steps with next / prev / left / right --- #
def _three_tones(shift=0.0):
    fs, n = 1000.0, 8192
    t = np.arange(n) / fs
    x = (np.exp(2j*np.pi*(100 + shift)*t) + 0.3*np.exp(2j*np.pi*-200*t) + 0.1*np.exp(2j*np.pi*300*t)
         + 1e-3*np.random.default_rng(0).standard_normal(n))
    return x.astype(np.complex64)

def test_peak_marker_stays_and_steps():
    model = FakeModel(nfft=1024)
    src = Source(model)
    p = PLOTS.get("PSD")(src, unit="dBFS", vbw=0)
    mid = p.markers.add("peak", threshold="-60")
    feed(src, model, _three_tones())
    def at():
        f = p.update()
        return round(next(m.x for m in f.axes[0].markers if m.label == mid))
    act = lambda a: p.markers.act(mid, a, p, p.last, p.bin_freqs(len(p.last)))
    assert at() == 100 # the highest
    act("next")
    assert at() == -200
    act("next")
    assert at() == 300
    with pytest.raises(ValueError, match="no peak lower"):
        act("next") # the threshold keeps it off the noise
    act("prev")
    assert at() == -200
    act("right")
    assert at() == 100 # the nearest peak above in frequency
    act("left")
    assert at() == -200
    feed(src, model, _three_tones(shift=60.0)) # the tone it is not on moves, and it stays put
    assert at() == -200
    p.markers.set(mid, "freq", "")
    assert at() == 160 # blank: lands on the highest again
    feed(src, model, _three_tones(shift=20.0))
    assert at() == 160 # and stays there
    p.markers.set(mid, "track", True)
    assert at() == 120 # tracking follows it
    assert p.markers.describe()[0]["actions"] == ["prev", "next", "left", "right"]
    with pytest.raises(ValueError, match="no action"):
        p.markers.act(p.markers.add("point", freq="0"), "next", p, p.last, p.bin_freqs(len(p.last)))

def test_peak_marker_is_dragged_by_frequency():
    model = FakeModel(nfft=1024)
    src = Source(model)
    p = PLOTS.get("PSD")(src)
    p.markers.add("peak")
    feed(src, model, _three_tones())
    m = p.update().axes[0].markers[0]
    assert (m.owner, m.edit) == ("M1", "freq")

def test_surface_spectrogram_frame():
    from pyspecan.plots.frame import Frame
    model = FakeModel(nfft=256)
    src = Source(model)
    p = PLOTS.get("Surface Spectrogram")(src, max_count=8, points=64)
    p.markers.add("channel", freq="100", bw="50")
    for i in range(10):
        feed(src, model, _two_tones(1024, nfft=256, seed=i))
        f = p.update()
    ax = f.axes[0]
    assert ax.projection == "3d" and ax.surface is not None and ax.surface.data.shape == (8, 64) and ax.surface.data.dtype == np.uint8
    assert (ax.ymin, ax.ymax) == (0, 7) and ax.zmin < ax.zmax
    col = int(round((100 - ax.xmin) / (ax.xmax - ax.xmin) * 63))
    row = ax.surface.data[0].astype(int)
    assert row[col - 1:col + 2].max() > np.median(row) + 60 # the strong tone stands up, in the newest row (in front)
    assert [(b.lo, b.hi, b.ylo, b.yhi) for b in ax.bands if b.label == "M1"] == [(75.0, 125.0, None, None)] # on the floor
    d = Frame([ax]).to_dict()["axes"][0]["surface"]
    assert (d["rows"], d["cols"]) == (8, 64) and isinstance(d["data"], str)

# --- reference traces and trace math --- #
def test_reference_trace_and_trace_math():
    model = FakeModel(nfft=1024)
    src = Source(model)
    p = PLOTS.get("PSD")(src, unit="dBFS", vbw=0, points=0, math="live - ref")
    assert p.ACTIONS == ("store ref", "clear ref")
    with pytest.raises(ValueError, match="nothing to store"):
        p.act("store ref")
    feed(src, model, _two_tones(4096))
    f = p.update()
    assert len(f.axes) == 1 and dict(f.readout)["Trace math"].startswith("store") # nothing to subtract yet
    p.act("store ref")
    feed(src, model, (_two_tones(4096) * 2).astype(np.complex64)) # 6 dB up everywhere
    f = p.update()
    assert [t.name for t in f.axes[0].traces][0] == "ref" and len(f.axes) == 2
    diff = f.axes[1].traces[0].y
    np.testing.assert_allclose(diff, 20 * np.log10(2), atol=0.05)
    assert dict(f.readout)["live - ref"].startswith("mean +6.02")
    p.set("ref_show", False)
    assert "ref" not in [t.name for t in p.update().axes[0].traces] and len(p.update().axes) == 2 # hidden, math still on
    p.set("unit", "dB/Hz") # another unit: the reference no longer compares
    feed(src, model, _two_tones(4096))
    assert len(p.update().axes) == 1
    p.set("unit", "dBFS")
    feed(src, model, _two_tones(4096))
    p.update()
    p.act("store ref")
    p.act("clear ref")
    assert len(p.update().axes) == 1

def test_reference_survives_an_fft_size_change():
    model = FakeModel(nfft=1024)
    src = Source(model)
    p = PLOTS.get("PSD")(src, unit="dBFS", vbw=0, points=0, math="live - ref", window="flattop")
    feed(src, model, _two_tones(4096))
    p.update()
    p.act("store ref")
    model.nfft = 2048 # finer bins: the reference is interpolated onto them
    p.reset()
    feed(src, model, _two_tones(8192))
    f = p.update()
    d = f.axes[1].traces[0]
    on = int(np.argmin(np.abs(d.x - 100))) # on the tone's peak both read its level (its skirts and the floor follow the RBW)
    assert abs(d.y[on]) < 0.5

# --- wavelet scalogram --- #
def test_scalogram_places_tones_in_time_and_frequency():
    fs, n = 1e6, 16384
    t = np.arange(n) / fs
    x = np.where(t < t[-1] / 2, np.exp(2j*np.pi*20e3*t), np.exp(2j*np.pi*-200e3*t)) # 20 kHz, then -200 kHz
    model = FakeModel(fs=fs, nfft=1024)
    src = Source(model)
    feed(src, model, (x + 1e-3 * np.random.default_rng(0).standard_normal(n)).astype(np.complex64))
    def peak(side, col):
        ax = PLOTS.get("Scalogram")(src, side=side).update().axes[0]
        img = ax.image.data.astype(float)
        rows = img.shape[0]
        f = 10 ** (ax.ymax - (np.arange(rows) + 0.5) / rows * (ax.ymax - ax.ymin))
        return f[np.argmax(img[:, col])], img[:, col].max()
    f1, _ = peak("upper", 128)
    assert abs(f1 / 20e3 - 1) < 0.06 # 20 kHz in the first half
    f2, _ = peak("lower", 384)
    assert abs(f2 / 200e3 - 1) < 0.06 # -200 kHz (below the tuned frequency) in the second half
    _, low = peak("upper", 384)
    assert low < 200 # nothing above the tuned frequency then
    ax = PLOTS.get("Scalogram")(src).update().axes[0]
    assert ax.yfmt == "logfreq" and ax.xfmt == "time" and ax.image.data.shape == (128, 512)

def test_plot_actions_through_the_controller():
    from pyspecan.plots.base import Plot
    assert Plot.ACTIONS == ()


# --- what the plot picker tells about each plot --- #
def test_every_plot_says_what_it_does():
    from pyspecan.plots.base import CATEGORIES
    for name in PLOTS.names():
        cls = PLOTS.get(name)
        a = cls.about()
        assert cls.CATEGORY in CATEGORIES and cls.CATEGORY != "Other", name
        assert a["data"] and a["shows"] and a["use"] and a["cost"], name # Data, Shows, Use, Cost
        assert all(u and u[0].isupper() for u in a["use"]), name

def test_about_of_a_plot_that_says_nothing():
    from pyspecan.plots.base import Plot, about_text, cost_text
    class Bare(Plot):
        """Something an extension added"""
        CATEGORY = "Not a category"
    a = Bare.about()
    assert a == {"category": "Other", "data": "", "shows": "Something an extension added", "use": [], "cost": ""}
    assert about_text("Bare", a) == "Bare (Other)\nShows: Something an extension added" # no empty lines
    assert (cost_text(None), cost_text(0.5), cost_text(3), cost_text(16)) == ("", "light, about 0.5x a PSD",
                                                                                "medium, about 3x a PSD", "heavy, about 16x a PSD")

# --- update every N blocks --- #
def test_update_every_skips_blocks_but_not_redraws():
    from pyspecan.plots import layout
    model = FakeModel(nfft=256)
    src = Source(model)
    p = PLOTS.get("PSD")(src, every=3)
    drawn = []
    for i in range(7):
        feed(src, model, _two_tones(1024, nfft=256, seed=i))
        drawn.append(p.update() is not None)
    assert drawn == [True, False, False, True, False, False, True] # the 1st, 4th and 7th block
    feed(src, model, _two_tones(1024, nfft=256))
    assert p.update() is None # skipped...
    p.markers.add("peak")
    assert p.update() is not None # ...but the same block again (a redraw after an edit) renders
    assert all(any(s.key == "every" for s in PLOTS.get(n).SETTINGS) for n in PLOTS.names()) # every plot has it
    layout.validate(layout.parse_inline(["Persistence every=4"]))

# --- export --- #
def test_export_traces_table_and_json():
    import csv
    import io

    from pyspecan.plots.export import frame_json, table_csv, traces_csv
    model = FakeModel(nfft=256)
    src = Source(model)
    p = PLOTS.get("PSD")(src, unit="dBFS", points=0, t2_mode="blank", t3_mode="blank")
    p.markers.add("peak")
    feed(src, model, _two_tones(1024, nfft=256))
    f = p.update()
    rows = list(csv.reader(io.StringIO(traces_csv(f))))
    assert rows[0] == ["axis", "label", "trace", "x", "y"] and len(rows) == 1 + 256 # one row a point, no z column in 2d
    xs = [float(r[3]) for r in rows[1:]]
    np.testing.assert_allclose(xs, p.bin_freqs(256)) # x as views draw it: the bins' frequencies
    assert {r[2] for r in rows[1:]} == {"t1"}
    t = list(csv.reader(io.StringIO(table_csv(f))))
    assert t[0] == f.table.columns and t[1][1] == "peak"
    assert json.loads(frame_json(f))["axes"][0]["traces"][0]["name"] == "t1"
    iq = PLOTS.get("IQ 3D")(src).update()
    rows = list(csv.reader(io.StringIO(traces_csv(iq))))
    assert rows[0][-1] == "z" and all(r[5] for r in rows[1:]) # 3d: z on every row
    assert table_csv(iq) == ""

# --- gated spectrum, marker trend, autocorrelation --- #
def bursty(n=8000, period=1000, on=300, f=0.2, seed=0):
    """A tone on for `on` of every `period` samples, over weak noise"""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    x = ((t % period) < on) * np.exp(2j * np.pi * f * t)
    return (x + 1e-3 * (rng.standard_normal(n) + 1j * rng.standard_normal(n))).astype(np.complex64)

def test_gated_psd_takes_only_the_frames_inside_the_burst():
    model = FakeModel(nfft=64)
    src = Source(model)
    free = PLOTS.get("PSD")(src, t1_mode="average", avg_count=1000)
    gated = PLOTS.get("PSD")(src, t1_mode="average", avg_count=1000, trig_mode="gated")
    feed(src, model, bursty())
    free.update()
    frame = gated.update()
    readout = dict(frame.readout)
    assert readout["Gate"] == "32 frames in 8 openings" # 4 whole frames of 64 in each 300 sample burst
    assert 4.0 < np.max(gated.last) - np.max(free.last) < 7.0 # not diluted by the 70% off (5.2 dB)
    assert np.median(gated.last) < np.median(free.last) - 20 # no frame cut by a burst's edge splatters over the span
    gate = frame.axes[-1]
    assert gate.xfmt == "time" and len(gate.bands) == 8
    level = next(mk for mk in gate.markers if mk.kind == "hline")
    assert level.edit == "gate_level" # dragged to set the level
    gated.set("gate_length", "0.05") # 50 samples at 1 kS/s: shorter than an FFT
    gated.set("gate_level", "-20")
    frame = gated.update()
    assert dict(frame.readout)["Gate"] == "waiting: open shorter than an FFT"
    assert gated.last is not None # the trace keeps what it had, like an analyzer waiting for its trigger

def test_gated_psd_says_why_before_anything_passes():
    model = FakeModel(nfft=64)
    src = Source(model)
    gated = PLOTS.get("PSD")(src, trig_mode="gated", gate_level="10")
    feed(src, model, bursty())
    frame = gated.update()
    assert dict(frame.readout)["Gate"] == "waiting: never over the level"
    assert frame.axes[-1].traces # the power to set the level by

def test_marker_values_give_numbers_with_units():
    model = FakeModel(nfft=64)
    src = Source(model)
    psd = PLOTS.get("PSD")(src, unit="dBFS")
    psd.markers.add("peak", track=True)
    psd.markers.add("obw")
    psd.markers.add("limit", level=10)
    feed(src, model, tone(640))
    psd.update()
    v = psd.marker_values
    assert v["M1 level"][1] == "dBFS" and v["M1 level"][0] == pytest.approx(0.0, abs=1.5)
    assert v["M1 freq"] == (pytest.approx(100.0, abs=10.0), "Hz")
    assert v["M2 obw"][1] == "Hz" and v["M3 margin"][1] == "dB"

def test_marker_trend_keeps_each_markers_numbers_over_time():
    model = FakeModel(nfft=64)
    src = Source(model)
    tr = PLOTS.get("Marker Trend")(src, unit="dBFS")
    frame = None
    for i in range(3):
        feed(src, model, tone(640, seed=i))
        frame = tr.update()
    assert dict(frame.readout)["Trend"] == "add a marker to trend what it measures"
    tr.markers.add("peak", track=True)
    tr.markers.add("channel", freq="100", bw="50")
    for i in range(4):
        feed(src, model, tone(640, seed=i) * (1 + i))
        frame = tr.update()
    assert [a.ylabel for a in frame.axes] == ["", "dBFS", "Hz"] # the spectrum, then one axis per unit
    level = next(t for t in frame.axes[1].traces if t.name == "M1 level")
    assert len(level.y) == 4 and np.all(np.diff(level.y) > 0) # louder every block
    assert level.x[-1] == 0.0 and level.x[0] == pytest.approx(-3 * 0.64) # seconds ago (640 samples at 1 kS/s)
    tr.markers.remove("M2")
    tr.set("spectrum", False)
    feed(src, model, tone(640))
    frame = tr.update()
    assert "M2 power" not in tr.trend
    assert frame.axes[0].ylabel == "dBFS" and frame.table is not None # the table stays without the spectrum

def test_autocorrelation_finds_a_repetition():
    model = FakeModel(nfft=64)
    src = Source(model)
    ac = PLOTS.get("Autocorrelation")(src, span="0.2") # 200 lags at 1 kS/s
    rng = np.random.default_rng(0)
    word = rng.standard_normal(50) + 1j * rng.standard_normal(50)
    feed(src, model, np.tile(word, 40).astype(np.complex64))
    frame = ac.update()
    readout = dict(frame.readout)
    assert readout["R1"].startswith("50 ms (20 Hz)")
    assert frame.axes[0].markers[0].x == pytest.approx(0.05)
    ac.set("scale", "dB")
    assert ac.update().axes[0].ymax == 0.0
