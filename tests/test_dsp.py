"""The DSP plots on rpps (pyspecan.plots.dsp): signal boxes, selection, constellation, eye diagram, network analyzer.
Skipped without rpps, except the checks that pyspecan works without it"""
import json
import os
import subprocess
import sys

import numpy as np
import pytest

from pyspecan.plots import PLOTS, PlotSet, Source
from pyspecan.plots.settings import HAVE_RPPS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
need_rpps = pytest.mark.skipif(not HAVE_RPPS, reason="needs rpps (pyspecan[dsp])")

FS = 1e6
BLOCK = 12500

class Model:
    """The parts of Model plots read"""
    def __init__(self, fs=FS, nfft=1024):
        self.fs, self.nfft, self.overlap = fs, nfft, 0.5
        self.samples = np.zeros(0, dtype=np.complex64)
    def get_fs(self):
        from pyspecan.obj import Frequency
        return Frequency.get(self.fs)
    def get_cf(self):
        from pyspecan.obj import Frequency
        return Frequency.get(0)
    def get_nfft(self): return self.nfft
    def get_overlap(self): return self.overlap
    def get_block(self): return self.samples

def modulated(points, n, baud, f0, beta=0.35, seed=0, channel=None):
    """n samples of random symbols from `points` through a root raised cosine, at f0 [Hz]"""
    from rpps.signal.filters.shaping import rrc_pulse
    rng = np.random.default_rng(seed)
    sps = FS / baud
    k = int(n / sps) + 40
    s = np.asarray(points)[rng.integers(0, len(points), k)]
    up = np.zeros(int(k * sps) + 1, complex)
    up[(np.arange(k) * sps).astype(int)] = s
    h = rrc_pulse(np.arange(-8 * sps, 8 * sps + 1) / sps, beta)
    x = np.convolve(up, h, "same")[:n]
    if channel is not None:
        x = np.convolve(x, channel)[:n]
    return x * np.exp(2j * np.pi * f0 * np.arange(n) / FS)

QPSK = np.array([1 + 1j, -1 + 1j, -1 - 1j, 1 - 1j]) / np.sqrt(2)

def capture(sig_points=QPSK, n=BLOCK * 8, baud=50e3, f0=150e3, channel=None, tone=True, seed=0):
    x = modulated(sig_points, n, baud, f0, channel=channel, seed=seed)
    if tone:
        x = x + 0.3 * np.exp(2j * np.pi * -200e3 * np.arange(n) / FS)
    rng = np.random.default_rng(seed + 1)
    return (x + 0.02 * (rng.standard_normal(n) + 1j * rng.standard_normal(n))).astype(np.complex64)

def setup(*names, **globals_):
    """A source and a PlotSet-like group of plots sharing their globals"""
    from pyspecan.plots.base import default_globals
    model = Model()
    src = Source(model)
    g = default_globals(**globals_)
    return model, src, [PLOTS.get(n)(src, globals=g) for n in names]

def run(model, src, plots, sig, blocks=4):
    frames = None
    for i in range(blocks):
        model.samples = sig[i * BLOCK:(i + 1) * BLOCK]
        src.tick()
        frames = [p.update() for p in plots]
    return frames

# --- without rpps --- #
def _py(code: str, env_extra: dict):
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"), **env_extra)
    return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120, check=False)

def test_pyspecan_runs_without_rpps(tmp_path):
    layout = tmp_path / "layout.json"
    layout.write_text(json.dumps({"globals": {"cal_db": -3, "dsp_freq": "150k", "dsp_mod": "qpsk"}, "rows": [[{"type": "PSD"}]]}))
    code = f"""
import sys
from pyspecan.plots import PLOTS, MARKER_KINDS, GLOBAL_SETTINGS, layout
assert "Constellation" not in PLOTS and "signals" not in MARKER_KINDS, PLOTS.names()
assert not any(g.key.startswith("dsp_") for g in GLOBAL_SETTINGS)
spec = layout.load({str(layout)!r}) # saved where rpps was installed: its analysis globals have nothing to set
layout.validate(spec)
assert spec.globals == {{"cal_db": -3}}, spec.globals
try:
    layout.parse_inline(["Constellation"])
except ValueError as e:
    assert "pyspecan[dsp]" in str(e), e
else:
    sys.exit("a DSP plot was accepted")
assert "rpps" not in sys.modules
print("ok")
"""
    out = _py(code, {"PYSPECAN_NO_RPPS": "1"})
    assert out.returncode == 0 and out.stdout.strip() == "ok", out.stderr

def test_importing_pyspecan_does_not_import_rpps():
    out = _py("import sys, pyspecan.plots; print('rpps' in sys.modules)", {})
    assert out.returncode == 0 and out.stdout.strip() == "False", out.stderr

# --- signals and the selection --- #
@need_rpps
def test_signals_marker_boxes_every_signal_and_marks_the_analysed_one():
    model, src, (psd,) = setup("PSD")
    psd.markers.add("signals")
    (f,) = run(model, src, [psd], capture())
    bands = {b.label: b for b in f.axes[0].bands}
    assert set(bands) == {"S1", "S2"}
    tone, qpsk = bands["S1"], bands["S2"]
    assert tone.lo < -200e3 < tone.hi and qpsk.lo < 150e3 < qpsk.hi and 50e3 < qpsk.hi - qpsk.lo < 75e3
    assert qpsk.color == "#5cb85c" and tone.color != qpsk.color # the strongest (widest power) is analysed
    assert all(b.owner == "" and b.edit == ("dsp_freq", "dsp_bw") for b in bands.values()) # a click sets the globals
    assert qpsk.ylo < qpsk.yhi and qpsk.yhi > f.axes[0].ymin # a box from the floor to the peak
    text = [" ".join(r.cells) for r in f.table.rows]
    assert any("S2" in t and "analysed" in t and "SNR" in t for t in text), text

@need_rpps
def test_a_click_on_a_box_selects_it_for_every_plot():
    from pyspecan.plots.drag import commit, hit_test
    model = Model()
    src = Source(model)
    plots = PlotSet(src)
    psd_id = plots.add("PSD")
    con_id = plots.add("Constellation")
    psd, con = plots.get(psd_id), plots.get(con_id)
    psd.markers.add("signals")
    run(model, src, [psd, con], capture())
    tone = next(b for b in psd.update().axes[0].bands if b.label == "S1")
    d = hit_test(psd.update().axes[0], 0, lambda x: x / 100, (tone.lo + tone.hi) / 200) # 100 Hz a pixel: its body
    op, owner, params = commit("off", d, False) # a plain click, nothing moved
    assert (op, owner, set(params)) == ("plot", "", {"dsp_freq", "dsp_bw"})
    for k, v in params.items():
        plots.set(psd_id, k, v)
    assert con.dsp_freq == params["dsp_freq"] # global: the constellation follows
    f = con.update()
    picked = dict(f.readout)["Signal"]
    assert abs(float(picked.split()[0]) + 200) < 2 and "(auto)" not in picked # the tone now (kHz), set by hand

@need_rpps
def test_selection_by_hand_and_the_strongest_is_sticky():
    from pyspecan.plots.dsp.analyzer import analyzer
    model, src, _ = setup()
    sig = capture()
    model.samples = sig[:BLOCK]
    src.tick()
    an = analyzer(src)
    auto = an.selection()
    assert auto.auto and abs(auto.freq - 150e3) < 5e3
    near = an.selection("-190k")
    assert not near.auto and abs(near.freq + 200e3) < 2e3 # the found signal nearest it
    box = an.selection("100k", "20k")
    assert (box.freq, box.width) == (100e3, 20e3) # exactly what was asked
    model.samples = sig[BLOCK:2 * BLOCK]
    src.tick()
    assert an.selection() is auto # the same signal found again: the same channel

# --- symbols --- #
@need_rpps
@pytest.mark.parametrize("mod, points", [
    ("qpsk", QPSK),
    ("8psk", np.exp(2j * np.pi * np.arange(8) / 8)),
    ("16QAM", (np.add.outer(np.arange(-3, 4, 2), 1j * np.arange(-3, 4, 2)).ravel()) / np.sqrt(10)),
])
def test_constellation_finds_the_modulation_and_rate(mod, points):
    model, src, (con,) = setup("Constellation")
    (f,) = run(model, src, [con], capture(points, baud=40e3, tone=False, seed=3))
    r = dict(f.readout)
    assert r["Mod"] == mod and r["Baud"] == "40 kBd", r
    assert float(r["EVM"].rstrip("%")) < 2.5, r # the rate tracked over the history: no timing drift
    syms, ideal = f.axes[0].traces
    assert len(ideal.y) == len(points) and len(syms.y) >= 500
    assert f.axes[0].square and f.axes[0].traces[0].kind == "scatter"

@need_rpps
def test_a_lock_is_followed_and_found_again_when_the_modulation_changes(monkeypatch):
    from pyspecan.plots.dsp import analyzer as an_mod
    monkeypatch.setattr(an_mod, "RECHECK_S", 0.0) # every block: the test does not wait a second
    model, src, (con,) = setup("Constellation")
    qpsk = capture(QPSK, baud=40e3, tone=False, seed=3)
    psk8 = capture(np.exp(2j * np.pi * np.arange(8) / 8), baud=40e3, tone=False, seed=4)
    (f,) = run(model, src, [con], qpsk)
    assert dict(f.readout)["Mod"] == "qpsk"
    first = an_mod.analyzer(src)._found
    assert len(first) == 1
    (f,) = run(model, src, [con], qpsk[4 * BLOCK:], blocks=2)
    assert dict(f.readout)["Mod"] == "qpsk" # followed, not searched again
    mods = [dict(run(model, src, [con], psk8[i * BLOCK:], blocks=1)[0].readout).get("Mod") for i in range(4)]
    assert mods[-1] == "8psk", mods # the lock went stale and the search found the new one

@need_rpps
def test_given_modulation_and_rate_are_used():
    model, src, (con,) = setup("Constellation", dsp_mod="bpsk", dsp_baud="50k")
    (f,) = run(model, src, [con], capture(tone=False))
    r = dict(f.readout)
    assert r["Mod"] == "bpsk" and r["Baud"] == "50 kBd" # what was asked, even if it fits badly
    assert float(r["EVM"].rstrip("%")) > 20.0

@need_rpps
def test_eye_diagram_opens_at_the_symbol_instants():
    model, src, (eye,) = setup("Eye Diagram", decay=0.0)
    (f,) = run(model, src, [eye], capture(tone=False))
    i_axis, q_axis = f.axes
    img = i_axis.image.data.astype(float)
    rows, cols = img.shape
    assert (rows, cols) == (96, 128) and q_axis.image is not None and (i_axis.xmin, i_axis.xmax) == (0.0, 2.0)
    zero = slice(rows // 2 - 3, rows // 2 + 3) # around 0 amplitude
    centre, crossing = cols // 2, cols // 4 # the instants at 0, 1, 2 symbols, the transitions half way between
    assert img[zero, crossing - 2:crossing + 3].sum() > 0
    assert img[zero, centre - 2:centre + 3].sum() < 0.05 * img[zero, crossing - 2:crossing + 3].sum() # open at the instant
    level = round((1 - (1 / np.sqrt(2)) / i_axis.ymax) * (rows - 1) / 2) # +0.707 at the instant
    assert img[level - 3:level + 4, centre].max() == img[:, centre].max()

@need_rpps
def test_nothing_to_lock_says_why():
    model, src, (con, eye, na) = setup("Constellation", "Eye Diagram", "Network Analyzer")
    rng = np.random.default_rng(0)
    noise = (0.01 * (rng.standard_normal(BLOCK * 2) + 1j * rng.standard_normal(BLOCK * 2))).astype(np.complex64)
    for f in run(model, src, [con, eye, na], noise, blocks=2):
        why = dict(f.readout).get("Lock", "")
        assert why == "no signal found" or "no symbol rate" in why, f.readout

@need_rpps
def test_silence_chosen_by_hand_says_why_and_raises_nothing():
    model, src, plots = setup("Constellation", "Cyclic Spectrum", dsp_freq="150k", dsp_bw="60k")
    con, cyc = run(model, src, plots, np.zeros(BLOCK * 4, np.complex64))
    assert "no signal" in dict(con.readout)["Lock"] or "too few" in dict(con.readout)["Lock"], con.readout
    assert cyc is not None

@need_rpps
def test_a_carrier_is_not_locked_to():
    model, src, (con,) = setup("Constellation", dsp_freq="-200k", dsp_bw="20k")
    (f,) = run(model, src, [con], capture())
    assert "no symbol rate" in dict(f.readout)["Lock"] and not f.axes[0].traces, f.readout

# --- network analyzer --- #
@need_rpps
def test_network_analyzer_measures_a_two_path_channel():
    echo, delay = 0.3, 4 # an echo 4 samples (4 us) later, 10 dB down
    model, src, (na,) = setup("Network Analyzer", decay=0.9)
    (f,) = run(model, src, [na], capture(tone=False, baud=100e3, channel=np.r_[1.0, np.zeros(delay - 1), echo]), blocks=8)
    mag = f.axes[0].traces[0]
    fb = mag.x # absolute frequencies across the band
    centre = 150e3
    expect = 20 * np.log10(np.abs(1 + echo * np.exp(-2j * np.pi * (fb - centre) * delay / FS)))
    expect -= np.mean(expect[np.abs(fb - centre) <= 100e3 / 4])
    inner = np.abs(fb - centre) <= 0.45 * 100e3 # away from the band edges, where there is little power
    assert np.max(np.abs(mag.y[inner] - expect[inner])) < 0.6, (mag.y[inner], expect[inner])
    ripple = float(dict(f.readout)["Ripple"].split()[0])
    assert abs(ripple - np.ptp(expect)) < 0.6, (ripple, np.ptp(expect))

@need_rpps
def test_network_analyzer_is_flat_for_a_clean_link():
    model, src, (na,) = setup("Network Analyzer")
    (f,) = run(model, src, [na], capture(tone=False), blocks=6)
    mag, phase, _gd = f.axes
    assert float(dict(f.readout)["Ripple"].split()[0]) < 0.5
    assert np.max(np.abs(phase.traces[0].y)) < 3.0 # degrees
    assert all(a.xfmt == "freq" for a in f.axes) and mag.xmin < 150e3 < mag.xmax

# --- the VSA plots --- #
EIGHT = np.exp(2j * np.pi * np.arange(8) / 8)

@need_rpps
def test_impulse_response_finds_an_echo():
    for taper in ("hann", "blackman"):
        model, src, (ir,) = setup("Impulse Response")
        ir.set("taper", taper)
        (f,) = run(model, src, [ir], capture(tone=False, channel=np.r_[1.0, np.zeros(79), 0.1]), blocks=6) # 80 us, -20 dB
        echo = dict(f.readout)["Echo"]
        assert echo.startswith("-20") or echo.startswith("-19"), f.readout
        assert echo.endswith("80 µs"), f.readout
        assert f.axes[0].xfmt == "time"
    model, src, (ir,) = setup("Impulse Response")
    (f,) = run(model, src, [ir], capture(tone=False), blocks=6)
    assert "Echo" not in dict(f.readout) # a clean link: the taper's sidelobes are not echoes

@need_rpps
def test_error_vector_and_summary():
    model, src, (ev, evs, con) = setup("Error Vector", "Error Vector Spectrum", "Constellation")
    frames = run(model, src, [ev, evs, con], capture(EIGHT, tone=False))
    r = dict(frames[0].readout)
    assert float(r["EVM"].split("%")[0]) < 2.5 and float(r["MER"].split()[0]) > 30
    assert abs(float(r["Gain imb"].split()[0])) < 0.3 and abs(float(r["Quad err"].rstrip("°"))) < 1
    assert [a.ylabel for a in frames[0].axes] == ["EVM (%)", "Mag err (%)", "Phase err (deg)"]
    assert float(dict(frames[1].readout)["Error / signal"].split()[0]) < -30 # a clean signal's error is far down
    assert "MER" in dict(frames[2].readout) # the constellation carries the summary too

@need_rpps
def test_cyclic_spectrum_finds_the_rate_blind():
    model, src, (cs,) = setup("Cyclic Spectrum")
    (f,) = run(model, src, [cs], capture(tone=False, baud=40e3))
    assert dict(f.readout)["Baud"].startswith("40 kBd")
    assert np.allclose([m.x for m in f.axes[0].markers], [-40e3, 40e3], atol=5) and f.axes[1].image is not None

@need_rpps
def test_symbol_table_and_3d_constellation():
    model, src, (st, c3) = setup("Symbol Table", "3D Constellation")
    st.set("count", 64)
    frames = run(model, src, [st, c3], capture(EIGHT, tone=False))
    table = frames[0].table
    assert table.columns[0] == "Symbol" and len(table.rows) == 8 and all(len(r.cells) == 9 for r in table.rows)
    assert {c for r in table.rows for c in r.cells[1:]} <= set("01234567")
    ax = frames[1].axes[0]
    assert ax.projection == "3d" and [t.name for t in ax.traces] == ["path", "syms"]
    syms = ax.traces[1]
    assert len(syms.x) == 48 and syms.kind == "scatter" and np.allclose(np.abs(syms.y + 1j * syms.z), 1, atol=0.1)

@need_rpps
def test_vector_diagram_and_constellation_density():
    model, src, (vd, cd) = setup("Vector Diagram", "Constellation Density")
    vd.set("count", 100)
    frames = run(model, src, [vd, cd], capture(tone=False))
    ax = frames[0].axes[0]
    path, syms, ideal = ax.traces
    assert (path.kind, syms.kind, len(syms.y), len(ideal.y)) == ("line", "scatter", 100, 4)
    assert len(path.y) > 8 * 90 # the matched filter's path, eight points a symbol
    assert ax.square and np.max(np.abs(path.x + 1j * path.y)) > 1.0 # it swings past the points between symbols
    ax = frames[1].axes[0]
    img = ax.image.data
    assert img.shape == (160, 160) and img.max() == 255 and ax.traces[0].name == "ideal"
    q = img.shape[0] // 2
    assert all(part.max() > 200 for part in (img[:q, :q], img[:q, q:], img[q:, :q], img[q:, q:])) # a cluster per quadrant
    assert img[q - 10:q + 10, q - 10:q + 10].max() == 0 # nothing at the origin

# --- decoding: rpps' profiles through rp.profile.Decoder --- #
def adsb_recording(path, frames=4, seed=1):
    """A SigMF recording of ADS-B squitters at 2 MS/s, 1090 MHz: (its meta path, the payloads)"""
    import rpps as rp
    from pysdrlib import FileSink
    rng = np.random.default_rng(seed)
    tx, s, waves, payloads = rp.profile.load("adsb/mode_s").tx(), None, [], []
    for i in range(frames):
        bits = rng.integers(0, 2, 83).astype(bool)
        payloads.append(np.packbits(bits).tobytes().hex())
        d = rp.Data(bits, Fs=2e6, sps=1, stream=s, flush=i == frames - 1)
        s = d.stream
        waves += [tx(d, fields={"df": 17}).data * 0.5, np.zeros(30000, np.complex64)]
    x = np.concatenate([np.zeros(20000, np.complex64)] + waves + [np.zeros(120000, np.complex64)]) # (blocks of 100k: none cut)
    x = (x + 0.01 * (rng.standard_normal(len(x)) + 1j * rng.standard_normal(len(x)))).astype(np.complex64)
    with FileSink(path / "adsb.sigmf", rate=2e6, freq=1090e6) as out:
        out.write(x)
    return path / "adsb.sigmf-meta", payloads

def decoding(meta, **settings):
    from pyspecan.config import Sink
    from pyspecan.controller.base import Controller
    from pyspecan.model.model import GetModel
    class Quiet(Controller):
        def __init__(self, model, **kw):
            super().__init__(model, None, **kw)
        def deliver(self, frames, status):
            pass
    kw = dict(path=str(meta), nfft=1024)
    c = Quiet(GetModel(Sink.FILE)(**kw), **kw)
    pid = c.add_plot("Decode")
    for k, v in settings.items():
        c.set_plot(pid, k, v)
    return c, pid

@need_rpps
def test_decode_lists_the_profiles_and_what_the_rate_can_run(tmp_path):
    meta, _ = adsb_recording(tmp_path, frames=1)
    c, pid = decoding(meta)
    c.step()
    f = c.latest[pid]
    fits = {r.cells[0]: r.cells[1] for r in f.table.rows}
    assert fits["adsb/mode_s"] == "yes" and fits["ieee80211b/long"].startswith("needs")
    assert "symbol rate" in fits["dvbs/qpsk"] # its rate is open
    with pytest.raises(ValueError, match="no profile"):
        c.set_plot(pid, "profile", "adsb/nope")

@need_rpps
def test_decode_reads_adsb_off_a_recording_newest_first_at_its_time(tmp_path):
    meta, payloads = adsb_recording(tmp_path)
    c, pid = decoding(meta, profile="adsb/mode_s")
    while c.step():
        pass
    f = c.latest[pid]
    r = dict(f.readout)
    assert r["State"] == "locked" and r["Messages"].startswith(f"{len(payloads)} good")
    rows = [row.cells for row in f.table.rows]
    assert [row[4] for row in rows] == payloads[::-1] # every frame, newest first, nothing failed listed
    assert all(row[1] == "frame" and row[2] == "ok" and row[3] == "df=17" for row in rows)
    import datetime as dt
    t0 = c.sink.dev.meta.start_time # the recording's start, plus each frame's place in it
    first = dt.datetime.strptime(rows[-1][0], "%H:%M:%S.%f").time()
    start = dt.datetime.fromtimestamp(t0, dt.timezone.utc)
    assert (dt.datetime.combine(start.date(), first, dt.timezone.utc) - start).total_seconds() == pytest.approx(0.01, abs=2e-3)
    good = f.axes[0].traces[0]
    assert sum(good.y) == len(payloads) # each block's good messages drawn
    c.set_plot(pid, "failed", True) # failed checks listed too, now
    c.command("reset")
    while c.step():
        pass
    assert any(row.cells[2] == "FAIL" for row in c.latest[pid].table.rows)

@need_rpps
def test_decode_says_why_it_cannot(tmp_path):
    meta, _ = adsb_recording(tmp_path, frames=1)
    c, pid = decoding(meta, profile="ieee80211b/long") # 22 MHz of channel at 2 MS/s
    c.step()
    assert "needs" in dict(c.latest[pid].readout)["Decode"]
