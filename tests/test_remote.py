"""A radio hosted by a pysdrlib server (tcp://host:port/<id>), against a local server hosting pysdrlib's simulated radio"""
import socket
import subprocess
import sys
import time

import numpy as np
import pytest

pytest.importorskip("zmq")
pysdrlib = pytest.importorskip("pysdrlib")
remote = pytest.importorskip("pysdrlib.remote")

from pyspecan.config import Sink
from pyspecan.controller.base import Controller

class Recorder(Controller):
    def __init__(self, model, **kwargs):
        super().__init__(model, None, **kwargs)
        self.ticks = []
    def deliver(self, frames, status):
        self.ticks.append(frames)
from pyspecan.model.model import GetModel

@pytest.fixture(scope="module")
def server():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    address = f"tcp://127.0.0.1:{port}"
    proc = subprocess.Popen([sys.executable, "-m", "pysdrlib", "server", "--bind", address, "--devices", "sim", "--open", "sim", "--no-shm"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(100):
            try:
                with remote.Client(address, 1.0) as c:
                    if c.list():
                        break
            except Exception:
                time.sleep(0.1)
        else:
            pytest.skip("could not start a pysdrlib server")
        yield address
    finally:
        proc.terminate()
        proc.communicate(timeout=10)

def hosted(address):
    with remote.Client(address, 2.0) as c:
        return {d["id"]: d for d in c.list()}

def make(address, ident="sim-0", **kw):
    return GetModel(Sink.LIVE)(device=f"{address}/{ident}", nfft=256, **kw)

def test_a_hosted_radio_nobody_controls_can_be_watched_but_not_tuned(server):
    sink = make(server).sink
    try:
        assert sink.ready() and not sink.controlling and sink.hosted
        assert sink.get_fs().raw > 0 and sink.get_cf().raw > 0 # what the radio is set to
        with pytest.raises(ValueError, match="--claim"):
            sink.set_fs("2M")
        with pytest.raises(ValueError, match="--claim"):
            sink.set_cf("90M")
        with pytest.raises(RuntimeError, match="not receiving"): # nobody started it
            sink.next(1024)
    finally:
        sink.close()
    assert "sim-0" in hosted(server) # watching left it hosted

def test_claiming_tunes_and_streams_and_closing_leaves_it_hosted_and_free(server):
    model = make(server, claim=True, Fs="2M", cf="90M")
    sink = model.sink
    try:
        assert sink.controlling and sink.dev.state["rx"]
        assert sink.get_fs().raw == 2e6 and sink.get_cf().raw == 90e6
        assert sink.next(4096) and sink.samples.dtype == np.complex64 and len(sink.samples) == 4096
        model.set_fs("1M")
        assert sink.get_fs().raw == 1e6
        assert hosted(server)["sim-0"]["controlled"] and hosted(server)["sim-0"]["state"]["rx"]
    finally:
        sink.close()
    info = hosted(server)["sim-0"]
    assert not info["controlled"] and not info["state"]["rx"] # still hosted, stopped, nobody in control
    make(server, claim=True).sink.close() # so it can be claimed again right away

def test_plots_run_on_a_remote_radio(server):
    model = make(server, claim=True, Fs="1M", cf="100M")
    c = Recorder(model, nfft=256)
    try:
        c.add_plot("PSD")
        c.add_plot("Spectrogram")
        c.command("next")
        frames = c.ticks[-1]
        assert len(frames) == 2 and all(f.axes for f in frames.values())
        assert c.source.freq_range() == (99.5e6, 100.5e6)
        c.add_marker("p1", "channel", freq="100M", bw="100k") # markers measure a remote radio like any other
        assert c.ticks[-1]["p1"].table.rows[0].cells[1] == "channel"
    finally:
        c.quit() # detaches
    assert not hosted(server)["sim-0"]["controlled"] and not hosted(server)["sim-0"]["state"]["rx"]

def test_bad_remote_names_fail_clearly(server):
    from pyspecan.model.sink.live import SinkLive
    for bad in ("tcp:/hackrf", "://host:5555", "tcp://", "tcp://host:5555/a/b"):
        with pytest.raises(ValueError):
            SinkLive.split_address(bad)
    assert SinkLive.split_address("tcp://10.0.10.35:5555/hackrf-6") == ("tcp://10.0.10.35:5555", "hackrf-6")
    assert SinkLive.split_address("tcp://10.0.10.35:5555") == ("tcp://10.0.10.35:5555", None)
    assert SinkLive.split_address("tcp://10.0.10.35:5555/") == ("tcp://10.0.10.35:5555", None)
    with pytest.raises(pysdrlib.err.NoDevice):
        make(server, ident="sim-99")

def test_watching_an_idle_radio_says_how_to_start_it(server):
    sink = make(server).sink
    try:
        with pytest.raises(RuntimeError, match="relaunch with --claim"):
            sink.next(1024)
    finally:
        sink.close()


# --- finding radios: --list, and picking one when none is named --- #
def start_server(*extra):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    address = f"tcp://127.0.0.1:{port}"
    proc = subprocess.Popen([sys.executable, "-m", "pysdrlib", "server", "--bind", address, "--devices", "sim", "--no-shm", *extra],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for _ in range(100):
        try:
            with remote.Client(address, 1.0) as c:
                c.types()
                return address, proc
        except Exception:
            time.sleep(0.1)
    proc.terminate()
    pytest.skip("could not start a pysdrlib server")

@pytest.fixture
def empty_server():
    address, proc = start_server() # hosts nothing, can open a sim
    yield address
    proc.terminate()
    proc.communicate(timeout=10)

def test_list_shows_hosted_radios_with_the_option_that_picks_each(server):
    from pyspecan.model.sink.live import list_devices
    text = "\n".join(list_devices(server))
    assert f"-s live -d {server}/sim-0" in text and "--claim" in text and "free" in text and "idle" in text
    assert f"-d {server}/sim  " in text or f"-d {server}/sim" in text # the type it can open
    assert "attached to this machine" in text
    with pytest.raises(ValueError):
        list_devices("tcp:/bad")

def test_list_cli_flag_prints_and_exits(server, capsys, monkeypatch):
    from pyspecan._internal import main as m
    monkeypatch.setattr(sys, "argv", ["pyspecan", "--list", "-d", server])
    m._main(m._process_args(m.define_args_with_view()))
    assert f"{server}/sim-0" in capsys.readouterr().out

def test_a_server_address_alone_picks_a_radio(server, empty_server):
    from pyspecan.model.sink.live import pick_remote
    assert pick_remote(server) == "sim-0"             # the one it hosts, to watch
    assert pick_remote(server, claim=True) == "sim-0" # free, so claimable
    assert pick_remote(empty_server) == "sim"         # hosts none: a new one of the first type it can open
    c = make(server, claim=True).sink                 # now it has a controller
    try:
        assert pick_remote(server) == "sim-0"         # still the one to watch
        with pytest.raises(pysdrlib.err.Busy):
            pick_remote(server, claim=True)           # nothing free to take
    finally:
        c.close()

def test_launching_with_just_the_server_address_connects(server, capsys):
    sink = GetModel(Sink.LIVE)(device=server, claim=True, nfft=256).sink
    try:
        assert sink.controlling and sink.hosted and sink.next(2048)
        assert "using sim-0" in capsys.readouterr().out
    finally:
        sink.close()
    assert not hosted(server)["sim-0"]["controlled"]

def test_a_new_radio_opened_through_an_empty_server_is_closed_with_us(empty_server):
    sink = GetModel(Sink.LIVE)(device=empty_server, nfft=256).sink
    try:
        assert sink.controlling and not sink.hosted # opened for us
        assert len(hosted(empty_server)) == 1 and sink.next(2048)
    finally:
        sink.close()
    assert hosted(empty_server) == {} # and gone with us

def test_no_device_named_uses_the_first_radio_found(monkeypatch, capsys):
    monkeypatch.setattr(pysdrlib, "find", lambda *a, **k: [pysdrlib.DeviceInfo(driver="sim", label="Simulated radio 0"), pysdrlib.DeviceInfo(driver="sim", label="Simulated radio 1")])
    for name in (None, "auto"):
        sink = GetModel(Sink.LIVE)(device=name, nfft=256).sink
        try:
            assert sink.ready() and sink.next(2048) and sink.samples.dtype == np.complex64
            assert "using Simulated radio 0 (1 more" in capsys.readouterr().out
        finally:
            sink.close()

def test_nothing_attached_says_what_to_do(monkeypatch):
    monkeypatch.setattr(pysdrlib, "find", lambda *a, **k: [])
    with pytest.raises(pysdrlib.err.NoDevice, match="--list"):
        GetModel(Sink.LIVE)(device=None, nfft=256)

def test_a_driver_name_and_serial_still_pick_the_radio(monkeypatch):
    seen = []
    real = pysdrlib.open
    monkeypatch.setattr(pysdrlib, "open", lambda what, **k: (seen.append((what, k)), real("sim"))[1])
    sink = GetModel(Sink.LIVE)(device="sim", serial="ABC123", nfft=256).sink
    sink.close()
    assert seen == [("sim", {"serial": "ABC123"})]
