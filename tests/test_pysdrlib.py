"""What pyspecan takes from pysdrlib 0.5: file formats and SigMF, a live radio's RxMeta (lost and skipped samples),
recording, and sweeping. Live parts run against pysdrlib's simulated radio"""
import time

import numpy as np
import pysdrlib
import pytest
from pysdrlib import FileSink, RxMeta

from pyspecan.config import Sink
from pyspecan.controller.base import Controller
from pyspecan.model.model import GetModel
from pyspecan.model.sink import live as live_mod
from pyspecan.plots.sweep import plan


class Recorder(Controller):
    def __init__(self, model, **kwargs):
        super().__init__(model, None, **kwargs)
        self.ticks = []
    def deliver(self, frames, status):
        self.ticks.append((frames, status))

def tones(n=4096):
    t = np.arange(n)
    return (np.exp(2j*np.pi*0.1*t) + 0.25*np.exp(-2j*np.pi*0.3*t)).astype(np.complex64)

# --- files --- #
def test_the_format_comes_from_the_extension(tmp_path):
    x = tones()
    (x * 100).astype(np.complex64).view(np.float32).astype(np.int16).tofile(tmp_path / "c.cs16") # int16 I, Q
    sink = GetModel(Sink.FILE)(path=str(tmp_path / "c.cs16"), Fs="1M", nfft=256).sink
    assert sink.get_fmt().name == "ci16t" and sink.max_samp == len(x) and not sink.note
    x.tofile(tmp_path / "c.cfile")
    sink.set_path(tmp_path / "c.cfile") # each file its own format
    assert sink.get_fmt().name == "cf32" and sink.max_samp == len(x)
    assert sink.next(len(x)) and np.allclose(sink.samples, x)

def test_a_name_that_says_nothing_is_read_as_cf32_and_says_so(tmp_path, capsys):
    tones().tofile(tmp_path / "capture.iq")
    c_kw = dict(Fs="1M", nfft=256)
    c = Recorder(GetModel(Sink.FILE)(**c_kw), **c_kw)
    c.setting("path", str(tmp_path / "capture.iq"))
    assert c.sink.get_fmt().name == "cf32" and "cf32" in c.message and "capture.iq" in c.message
    assert "-F" in capsys.readouterr().out

def test_a_format_given_holds_for_every_file(tmp_path):
    tones().tofile(tmp_path / "a.cs16") # its name says ci16, it is really cf32
    sink = GetModel(Sink.FILE)(path=str(tmp_path / "a.cs16"), fmt="cf32", Fs="1M", nfft=256).sink
    assert sink.get_fmt().name == "cf32"
    sink.set_fmt("ci8t")
    sink.set_path(tmp_path / "a.cs16")
    assert sink.get_fmt().name == "ci8t"

def _sigmf(tmp_path, rate=2e6, freq=433.92e6):
    with FileSink(tmp_path / "rec.sigmf", rate=rate, freq=freq) as out:
        out.write(tones())
    return tmp_path / "rec.sigmf-meta"

def test_a_sigmf_recording_brings_its_rate_and_frequency(tmp_path):
    meta = _sigmf(tmp_path)
    sink = GetModel(Sink.FILE)(path=str(meta), nfft=256).sink
    assert sink.get_fs().raw == 2e6 and sink.get_cf().raw == 433.92e6 and sink.max_samp == 4096
    assert sink.next(4096) and np.allclose(sink.samples, tones())

def test_rate_and_frequency_given_at_launch_win_over_the_recording_then_the_next_file_brings_its_own(tmp_path):
    meta = _sigmf(tmp_path)
    sink = GetModel(Sink.FILE)(path=str(meta), Fs="1M", cf="100M", nfft=256).sink
    assert sink.get_fs().raw == 1e6 and sink.get_cf().raw == 100e6
    sink.set_path(meta) # opened later: the recording's
    assert sink.get_fs().raw == 2e6 and sink.get_cf().raw == 433.92e6

def test_seeking_clamps_to_the_file(tmp_path):
    tones().tofile(tmp_path / "c.cfile")
    sink = GetModel(Sink.FILE)(path=str(tmp_path / "c.cfile"), Fs="1M", nfft=256).sink
    sink.seek(10**9)
    assert sink.cur_samp == 4096 and not sink.next(1)
    sink.seek(-5)
    assert sink.cur_samp == 0 and sink.next(16)

# --- a live radio: what pysdrlib says about each block --- #
@pytest.fixture
def radio():
    m = GetModel(Sink.LIVE)(device="sim", Fs="1M", cf="100M", nfft=256)
    yield m
    m.sink.close()

def scripted(sink, metas):
    """Make the radio's reads return blocks with these RxMeta, in turn"""
    it = iter(metas)
    def read(count, timeout=None, meta=False, latest=False, **kw):
        m = next(it)
        return np.ones(m.count, np.complex64), m
    sink.dev.read = read

def test_blocks_follow_each_other_unless_samples_were_lost_or_skipped(radio):
    sink = radio.sink
    m = lambda index, gaps=(), discarded=0: RxMeta(index=index, count=1000, freq=100e6, rate=1e6, gaps=gaps, discarded=discarded)
    scripted(sink, [m(0), m(1000), m(2000, gaps=((400, 50),)), m(3050), m(4057, gaps=((0, 7),)), m(5057),
                    m(9000, discarded=2943)])
    seen, where = [], []
    for _ in range(7):
        assert sink.next(1000)
        seen.append(sink.contiguous)
        where.append(sink.block_index)
    assert where == [0, 1000, 2000, 3050, 4057, 5057, 9000] # each block's place in the stream, lost samples counted
    # the first has nothing before it; a gap inside a block breaks it, the next follows it (the gap was inside it);
    # a gap at its start (already counted in its index) breaks a block, the next follows; samples skipped to show the newest break it too
    assert seen == [False, True, False, True, False, True, False]
    assert sink.dropped == 57 and sink.skipped == 2943
    live = sink.live_status()
    assert live["dropped"] == 57 and live["skipped"] == 2943 and live["recording"] is None

def test_a_block_is_timed_by_the_radio_when_its_clock_holds_a_date_else_by_the_host():
    from pyspecan.model.sink.live import block_time
    m = RxMeta(index=0, count=10, freq=1e8, rate=1e6, time=time.monotonic() - 0.5, hw_time=1.8e9)
    assert block_time(m, 0.25) == 1.8e9 + 0.25
    m = RxMeta(index=0, count=10, freq=1e8, rate=1e6, time=time.monotonic() - 0.5, hw_time=12.0) # counting from power-up
    assert abs(block_time(m) - (time.time() - 0.5)) < 0.05
    assert block_time(RxMeta(index=0, count=10, freq=1e8, rate=1e6)) is None

def test_a_break_skips_a_sequence_number_so_streams_start_over(radio):
    c = Recorder(radio, nfft=256)
    c.add_plot("PSD")
    m = lambda index: RxMeta(index=index, count=radio.get_block_size(), freq=100e6, rate=1e6)
    n = radio.get_block_size()
    scripted(radio.sink, [m(0), m(n), m(5 * n)])
    c.command("next"); c.command("next")
    seq = c.source.seq
    c.command("next") # 3n samples were lost
    assert c.source.seq == seq + 2
    assert all(not s.carry.size or s.seen == c.source.seq for s in c.source._streams.values())

def test_a_radio_that_is_gone_says_so(radio):
    def read(*a, **kw):
        raise pysdrlib.err.Lost("unplugged")
    radio.sink.dev.read = read
    with pytest.raises(ConnectionError, match="gone"):
        radio.sink.next(256)

def test_a_spectrum_mirrored_by_the_chain_is_turned_back(radio):
    sink = radio.sink
    x = np.exp(2j*np.pi*0.1*np.arange(1000)).astype(np.complex64)
    sink.dev.read = lambda count, **kw: (x[:count].copy(), RxMeta(index=0, count=count, freq=100e6, rate=1e6))
    sink.inverted, sink.dc_block = True, False
    assert sink.next(1000) and np.allclose(sink.samples, x.conj())

# --- recording --- #
def test_recording_keeps_every_sample_and_the_tuning(radio, tmp_path):
    c = Recorder(radio, nfft=256, record_dir=str(tmp_path))
    c.add_plot("PSD")
    path = c.start_record()
    assert c.playing and path.endswith(".sigmf-data") and str(tmp_path) in path and "100000000Hz" in path
    shown = 0
    for _ in range(20):
        c.step()
        shown += len(c.sink.samples)
        assert len(c.sink.samples) == radio.get_block_size()
    rec, written = c.sink.recording(), c.sink.recorder.count
    assert written >= shown and rec["seconds"] == round(written / 1e6, 3) # everything read, not just what was shown
    assert c.get_status()["radio_live"]["recording"]["path"] == path
    c.stop_record()
    assert "recorded" in c.message and c.sink.recording() is None
    f = pysdrlib.File(path)
    assert f.rate == 1e6 and f.freq == 100e6 and f.max_samp == written

def test_a_path_with_a_format_records_that_format(radio, tmp_path):
    sink = radio.sink
    path = sink.start_record(tmp_path / "x.cs16")
    for _ in range(3):
        sink.next(256)
    n = sink.recorder.count
    sink.stop_record()
    assert path.endswith("x.cs16") and pysdrlib.File(path).max_samp == n and pysdrlib.File(path).fmt.name == "ci16t"

def test_a_failing_recording_stops_and_says_why_without_stopping_the_display(radio, tmp_path):
    sink = radio.sink
    sink.start_record(tmp_path / "r.sigmf")
    def full(*a, **kw):
        raise OSError("No space left on device")
    sink.recorder.write = full
    assert sink.next(256) and len(sink.samples) == 256
    assert sink.recorder is None and "No space left" in sink.live_status()["record_error"]

def test_recording_needs_a_radio(tmp_path):
    tones().tofile(tmp_path / "c.cfile")
    kw = dict(path=str(tmp_path / "c.cfile"), Fs="1M", nfft=256)
    c = Recorder(GetModel(Sink.FILE)(**kw), **kw)
    with pytest.raises(ValueError, match="no radio"):
        c.command("record")

# --- a TCP IQ stream, in the sender's format --- #
@pytest.mark.parametrize("fmt, dtype, scale", [("ci16", np.int16, 32767), ("cu8", np.uint8, None), ("cf32", np.float32, 1)])
def test_tcpiq_reads_the_format_the_sender_sends(fmt, dtype, scale):
    import socket
    import threading
    x = (0.5 * tones(8192)).astype(np.complex64)
    iq = np.empty(2 * len(x), np.float64)
    iq[0::2], iq[1::2] = x.real, x.imag
    raw = (np.round(iq * 127.5 + 127.5) if scale is None else np.round(iq * scale) if dtype != np.float32 else iq).astype(dtype)
    srv = socket.create_server(("127.0.0.1", 0))
    port = srv.getsockname()[1]
    def send():
        conn, _ = srv.accept()
        with conn:
            conn.sendall(raw.tobytes())
            time.sleep(1.0)
    threading.Thread(target=send, daemon=True).start()
    m = GetModel(Sink.TCPIQ)(tcp_host="127.0.0.1", tcp_port=port, tcp_fmt=fmt, Fs="1M", nfft=256)
    try:
        got = []
        while sum(map(len, got)) < 4096:
            assert m.sink.next(1024)
            got.append(m.sink.samples)
        y = np.concatenate(got)[:4096]
        y = y / np.abs(y).max() * np.abs(x[:4096]).max() # whatever full scale each format reads at
        assert np.allclose(y, x[:4096], atol=0.02), fmt
    finally:
        m.sink.close()
        srv.close()

def test_tcpiq_shows_the_rate_samples_arrive_at_and_uses_it_when_asked():
    import socket
    import threading
    rate, block = 200e3, 2000 # paced at 200 kS/s, declared as 1 MS/s
    srv = socket.create_server(("127.0.0.1", 0))
    stop = threading.Event()
    def send():
        conn, _ = srv.accept()
        with conn:
            chunk = (0.5 * tones(block)).tobytes()
            t0 = time.monotonic()
            for k in range(10**6):
                if stop.is_set():
                    break
                wait = t0 + k * block / rate - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                conn.sendall(chunk)
    threading.Thread(target=send, daemon=True).start()
    m = GetModel(Sink.TCPIQ)(tcp_host="127.0.0.1", tcp_port=srv.getsockname()[1], Fs="1M", nfft=256)
    c = Recorder(m, nfft=256)
    try:
        with pytest.raises(ValueError, match="no measured rate"):
            c.setting("fs", "measured") # nothing measured yet
        end = time.monotonic() + 6
        while time.monotonic() < end and not (m.sink.stream_status()["measured"] and time.monotonic() > end - 3):
            m.sink.next(1000)
        st = c.get_status()["stream"]
        assert st["peer"] and st["declared"] == 1e6 and st["mismatch"]
        assert st["measured"] == pytest.approx(rate, rel=0.05)
        assert m.get_fs().raw == 1e6 # shown, not applied
        c.setting("fs", "measured")
        assert m.get_fs().raw == pytest.approx(rate, rel=0.05) and m.get_fs().raw == float(f"{m.get_fs().raw:.4g}")
        assert not c.get_status()["stream"]["mismatch"]
    finally:
        stop.set()
        m.sink.close()
        srv.close()

def test_the_file_format_option_points_tcpiq_to_its_own():
    from pyspecan.arguments import hint
    from pyspecan.config import View
    assert "--tcp_fmt" in hint("F", View.WEB, Sink.TCPIQ)

# --- sweeping --- #
def test_the_sweep_plan_tiles_the_span_on_one_grid():
    centers, keep = plan(88e6, 108e6, 1e6, 1024)
    df = 1e6 / 1024
    assert keep % 2 == 0 and keep <= 0.8 * 1024
    assert np.allclose(np.diff(centers), keep * df) # each step starts where the last one's kept bins end
    assert centers[0] - keep * df / 2 == 88e6 and centers[-1] + keep * df / 2 >= 108e6
    with pytest.raises(ValueError):
        plan(108e6, 88e6, 1e6, 1024)

@pytest.fixture
def tone_radio(monkeypatch):
    """The sim radio hearing one carrier at 101.2 MHz, wherever it is tuned"""
    real = pysdrlib.open
    monkeypatch.setattr(live_mod.pysdrlib, "open", lambda name, **kw: real(
        name, tones=[{"freq": 101.2e6, "level": -10}], noise=-70, seed=1, **kw))
    m = GetModel(Sink.LIVE)(device="sim", Fs="1M", cf="100M", nfft=1024)
    yield m
    m.sink.close()

def test_the_sweep_finds_a_carrier_outside_the_tuned_span_and_tunes_back(tone_radio):
    c = Recorder(tone_radio, nfft=1024)
    assert "Sweep" in c.plot_types
    pid = c.add_plot("Sweep")
    c.set_plot(pid, "start", "98M")
    c.set_plot(pid, "stop", "104M")
    c.step()
    frame = c.latest[pid]
    plot = c.plots.get(pid)
    assert frame.axes[0].xmin == 98e6 and frame.axes[0].xmax == 104e6 and dict(frame.readout)["Steps"] == "8"
    freqs = plot.bin_freqs(len(plot.last))
    assert freqs[0] >= 98e6 and freqs[-1] <= 104e6 and np.allclose(np.diff(freqs), 1e6 / 1024)
    peak = freqs[np.argmax(plot.last)]
    assert abs(peak - 101.2e6) < 3e3 # outside 99.5-100.5 MHz, where the radio is tuned
    far = np.abs(freqs - 101.2e6) > 50e3
    assert plot.last[far].max() < plot.last.max() - 40 # and nowhere else: each step hears only what it covers
    assert tone_radio.sink.dev.get_rx_freq() == 100e6 and tone_radio.sink._next_index is None # tuned back, a break
    c.step() # and the next block is back at the center frequency
    assert c.sink.get_cf().raw == 100e6

def test_a_sweep_is_not_offered_for_a_file_and_says_why_without_control(tmp_path, tone_radio):
    tones().tofile(tmp_path / "c.cfile")
    kw = dict(path=str(tmp_path / "c.cfile"), Fs="1M", nfft=256)
    assert "Sweep" not in Recorder(GetModel(Sink.FILE)(**kw), **kw).plot_types
    c = Recorder(tone_radio, nfft=1024)
    pid = c.add_plot("Sweep")
    tone_radio.sink.start_record(tmp_path / "r.sigmf") # a sweep would retune the radio under the recording
    c.step()
    assert "recording" in dict(c.latest[pid].readout)["Sweep"]
    tone_radio.sink.stop_record()
