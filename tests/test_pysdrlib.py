"""What pyspecan takes from pysdrlib 0.5: file formats and SigMF recordings"""
import numpy as np
from pysdrlib import FileSink

from pyspecan.config import Sink
from pyspecan.controller.base import Controller
from pyspecan.model.model import GetModel


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
    with FileSink(tmp_path / "rec.sigmf", rate=rate, freq=freq, open=True) as out:
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
