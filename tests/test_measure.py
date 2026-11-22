import numpy as np
import pytest

from pyspecan import measure as m
from pyspecan.measure import windows

N = 4096
FS = 1e6

def _spectra(x, name):
    w = windows.window(name, len(x))
    return np.fft.fftshift(np.fft.fft(x * w))[None], w

def _noise(n, var, seed=0):
    r = np.random.default_rng(seed)
    return np.sqrt(var / 2) * (r.standard_normal(n) + 1j * r.standard_normal(n))

@pytest.mark.parametrize("name,expect,tol", [("rect", 1.0, 1e-9), ("hanning", 1.5, 0.01), ("blackman", 1.73, 0.01), ("flattop", 3.77, 0.02)])
def test_enbw(name, expect, tol):
    assert m.enbw(windows.window(name, 8192)) == pytest.approx(expect, abs=tol)

def test_flattop_tone_amplitude():
    A = 0.5
    k = np.arange(N)
    for off in (0.0, 0.25, 0.5):
        x = A * np.exp(2j * np.pi * (300 + off) * k / N)
        sp, w = _spectra(x, "flattop")
        db = m.scale(sp, FS, w, "dBFS")[0]
        assert db.max() == pytest.approx(20*np.log10(A), abs=0.1)

def test_full_scale_tone_is_0dbfs():
    x = np.exp(2j * np.pi * 300 * np.arange(N) / N)
    for name in windows.WindowLUT:
        sp, w = _spectra(x, name)
        assert m.scale(sp, FS, w, "dBFS")[0].max() == pytest.approx(0.0, abs=0.01)

def test_dbm_calibration():
    sp, w = _spectra(np.exp(2j * np.pi * 300 * np.arange(N) / N), "hanning")
    assert m.scale(sp, FS, w, "dBm", cal_db=-10, ext_gain_db=20)[0].max() == pytest.approx(-30, abs=0.01)

@pytest.mark.parametrize("name", list(windows.WindowLUT))
def test_noise_density(name):
    var = 0.25
    rows = np.vstack([_spectra(_noise(N, var, s), name)[0] for s in range(200)])
    w = windows.window(name, N)
    db = m.scale(rows, FS, w, "dB/Hz")
    mean = m.lin_to_db(np.mean(m.db_to_lin(db)))
    assert mean == pytest.approx(10*np.log10(var/FS), abs=0.15)

def test_full_band_power_and_rbw():
    var = 0.25
    sp, w = _spectra(_noise(N, var), "blackman")
    lin = m.db_to_lin(m.scale(sp, FS, w, "dB/Hz")[0])
    freqs = np.fft.fftshift(np.fft.fftfreq(N, 1/FS))
    assert m.band_power(lin, freqs, -FS/2, FS/2) == pytest.approx(var, rel=0.1)
    assert m.rbw(FS, N, w) == pytest.approx(1.73 * FS / N, rel=0.01)

def _bandlimited(n, lo, hi, seed=1):
    spec = np.fft.fftshift(np.fft.fft(_noise(n, 1.0, seed)))
    f = np.fft.fftshift(np.fft.fftfreq(n, 1/FS))
    spec[(f < lo) | (f >= hi)] = 0
    return np.fft.ifft(np.fft.ifftshift(spec))

def _density(x, name="hanning", frames=40):
    n = 4096
    rows = np.vstack([_spectra(x[i*n:(i+1)*n], name)[0] for i in range(len(x)//n)][:frames])
    w = windows.window(name, n)
    lin = np.mean(m.db_to_lin(m.scale(rows, FS, w, "dB/Hz")), axis=0)
    return lin, np.fft.fftshift(np.fft.fftfreq(n, 1/FS))

def test_obw_and_acpr():
    x = _bandlimited(4096*40, -100e3, 100e3)
    lin, f = _density(x)
    lo, hi, _ = m.obw(lin, f, -FS/2, FS/2, 99)
    assert hi - lo == pytest.approx(200e3, rel=0.05)
    main, lower, upper = m.acpr(lin, f, 0, 180e3, [300e3])
    assert main > 0 and lower[0] < -40 and upper[0] < -40

def test_xdb_bw():
    f = np.linspace(-1, 1, 2001)
    y = -f**2 * 100
    lo, hi = m.xdb_bw(y, f, 1000, 26)
    assert hi == pytest.approx(np.sqrt(0.26), abs=1e-3) and lo == pytest.approx(-hi, abs=1e-3)

def test_ccdf():
    c = m.CCDF()
    c.update(np.exp(2j * np.pi * 0.01 * np.arange(10000)) * 0.3)
    s = c.stats()
    assert abs(s["papr"]) < 0.01 and abs(s["p1"]) < 0.3
    g = m.CCDF()
    g.update(_noise(500000, 1.0))
    assert g.stats()["p1"] == pytest.approx(6.6, abs=0.3)
    x, p = g.curve()
    assert len(x) == len(p) and np.all(np.diff(p) <= 0)

def test_find_peaks():
    r = np.random.default_rng(0)
    y = r.standard_normal(2000) * 0.5 - 80
    for i, a in ((300, -20), (900, -30), (1500, -50)):
        y[i] = a
    idx = m.find_peaks(y, 5, excursion_db=6)
    assert list(idx) == [300, 900, 1500]
    assert list(m.find_peaks(y, 2)) == [300, 900]
    assert list(m.find_peaks(y, 5, threshold=-40)) == [300, 900]
    pos, lvl = m.interp(np.array([-3.0, 0.0, -1.0]), 1)
    assert 1 < pos < 1.5 and lvl >= 0

def test_detector():
    y = np.arange(100, dtype=float)
    x, p = m.reduce(y, 10, "peak")
    assert list(p) == list(range(9, 100, 10)) and len(x) == 10
    assert list(m.reduce(y, 10, "neg")[1]) == list(range(0, 100, 10))
    assert m.reduce(y, 0)[1] is y or np.array_equal(m.reduce(y, 0)[1], y)
    flat = np.full(100, -30.0)
    assert m.reduce(flat, 7, "rms")[1] == pytest.approx(-30.0)
    tone = np.full(100, -100.0); tone[3] = 0.0
    assert m.reduce(tone, 10, "rms")[1][0] == pytest.approx(-10.0, abs=0.01)
    assert m.reduce(np.vstack([y, y]), 10, "peak")[1].shape == (2, 10)

def test_averager():
    for mode in ("power", "log", "exp"):
        a = m.Averager(mode, 4)
        out = a.update(np.full((6, 16), -40.0))
        assert out == pytest.approx(-40.0)
    a = m.Averager("power", 2)
    a.update(np.array([[0.0] * 4]))
    out = a.update(np.array([[-100.0] * 4]))
    assert out[0] == pytest.approx(10*np.log10(0.5 + 0.5e-10), abs=1e-6) and a.n == 2
    a.update(np.array([[-100.0] * 4]))
    assert a.update(np.array([[-100.0] * 4]))[0] == pytest.approx(-100.0, abs=0.01)
    a.reset()
    assert a.n == 0
    assert m.Averager("off").update(np.array([[1.0, 2.0]])).tolist() == [1.0, 2.0]

# --- trigger --- #
from pyspecan.measure import trigger as trig


def test_trigger_finds_edges_interpolated():
    ramp = np.array([-1.0, -0.5, 0.0, 0.5, 1.0, 0.5, 0.0, -0.5, -1.0])
    np.testing.assert_allclose(trig.find(ramp, 0.25, "rising"), [2.5])
    np.testing.assert_allclose(trig.find(ramp, 0.25, "falling"), [5.5])

def test_trigger_on_sine_and_spacing():
    sig = np.sin(2*np.pi*np.arange(1000)/100 + 0.1)
    rising = trig.find(sig, 0.0, "rising")
    assert len(rising) == 10
    np.testing.assert_allclose(np.diff(rising), 100, atol=1e-3)
    thinned = trig.find(sig, 0.0, "rising", spacing=250)
    np.testing.assert_allclose(np.diff(thinned), 300, atol=1e-3) # next crossing at least 250 later
    with pytest.raises(ValueError):
        trig.find(sig, 0.0, "sideways")

def test_trigger_signal_sources():
    x = np.array([3+4j], dtype=np.complex64)
    assert trig.signal(x, "I")[0] == 3 and trig.signal(x, "Q")[0] == 4 and trig.signal(x, "Mag")[0] == 5

def test_envelope_keeps_short_spikes():
    sig = np.zeros(10_000)
    sig[1234] = 7.0
    sig[8000] = -3.0
    mn, mx = trig.envelope(sig, 100)
    assert len(mn) == len(mx) == 100
    assert mx.max() == 7.0 and mn.min() == -3.0
    assert np.count_nonzero(mx) == 1 and np.count_nonzero(mn) == 1
    small = np.arange(5.0)
    assert trig.envelope(small, 100)[0] is small

# --- gate --- #
def test_gate_spans_open_on_the_level_with_delay_and_length():
    p = np.full(100, -60.0)
    p[20:50] = p[70:90] = -10.0
    assert m.trigger.gate_spans(p, -30.0) == [(20, 50), (70, 90)]
    assert m.trigger.gate_spans(p, -30.0, delay=5) == [(25, 50), (75, 90)]
    assert m.trigger.gate_spans(p, -30.0, delay=5, length=10) == [(25, 35), (75, 85)]
    assert m.trigger.gate_spans(p, 0.0) == []
    p[:5] = -10.0 # on from the start: no edge to delay from
    assert m.trigger.gate_spans(p, -30.0, delay=5)[0] == (0, 5)

def test_gate_frames_fit_inside_the_spans():
    starts = m.trigger.frame_starts([(10, 50), (60, 70), (100, 164)], 16)
    np.testing.assert_array_equal(starts, [10, 26, 100, 116, 132, 148]) # 148 ends at 164, the span's end

def test_gate_power_and_auto_level():
    x = np.zeros(1000, complex)
    x[300:600] = 1.0
    p = m.trigger.power_db(x)
    assert p[400] == pytest.approx(0.0) and p[100] < -200
    assert m.trigger.power_db(x, 10)[305] == pytest.approx(10 * np.log10(0.6), abs=1e-6) # smoothed over 10
    lvl = m.trigger.auto_level(m.trigger.power_db(x + 1e-3))
    assert -60 < lvl < 0

# --- autocorrelation --- #
def test_autocorr_is_one_at_zero_and_peaks_at_the_period():
    rng = np.random.default_rng(0)
    word = rng.standard_normal(37) + 1j * rng.standard_normal(37)
    x = np.tile(word, 40) + 0.3 * (rng.standard_normal(37 * 40) + 1j * rng.standard_normal(37 * 40))
    r = m.correlate.autocorr(x, 200)
    assert r[0] == pytest.approx(1.0) and len(r) == 201
    lag, v = m.correlate.peaks(r, 1)[0]
    assert lag == 37 and v > 0.8

def test_autocorr_of_noise_has_no_peak_over_its_floor():
    rng = np.random.default_rng(1)
    n = 20000
    r = m.correlate.autocorr(rng.standard_normal(n) + 1j * rng.standard_normal(n), 500)
    assert m.correlate.lobe_end(r) <= 2
    assert m.correlate.peaks(r, 3, floor=4 / np.sqrt(n)) == []

def test_autocorr_removes_dc():
    x = np.ones(1000) + 0.01 * np.random.default_rng(2).standard_normal(1000)
    assert m.correlate.autocorr(x, 10, remove_dc=False)[5] > 0.99
    assert m.correlate.autocorr(x, 10)[5] < 0.2
