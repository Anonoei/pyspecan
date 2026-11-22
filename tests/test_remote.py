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

def short(address):
    """How pysdrlib writes a server in a target: tcp://127.0.0.1:5556 -> 127.0.0.1:5556"""
    return pysdrlib.targets.short(address)

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
    c = Recorder(model, nfft=256, layout_items=["PSD", "Spectrogram"])
    try:
        c.command("next")
        frames = c.ticks[-1]
        assert len(frames) == 2 and all(f.axes for f in frames.values())
        assert c.source.freq_range() == (99.5e6, 100.5e6)
        c.add_marker("p1", "channel", freq="100M", bw="100k") # markers measure a remote radio like any other
        assert c.ticks[-1]["p1"].table.rows[0].cells[1] == "channel"
    finally:
        c.quit() # detaches
    assert not hosted(server)["sim-0"]["controlled"] and not hosted(server)["sim-0"]["state"]["rx"]

def test_targets_name_a_radio_on_a_server_however_it_is_written(server):
    from pyspecan.model.sink.live import remote_target
    t = remote_target("10.0.10.35/hackrf-6")
    assert t.server == "tcp://10.0.10.35:5555" and t.device == "hackrf-6"
    assert remote_target("tcp://10.0.10.35:5556").device is None # the server picks
    assert remote_target("hackrf@a06") is None and remote_target("auto") is None and remote_target(None) is None
    for name in (f"{server}/sim-0", f"{short(server)}/sim-0"): # with or without the scheme
        sink = GetModel(Sink.LIVE)(device=name, nfft=256).sink
        try:
            assert sink.remote and sink.hosted and sink.server == server and sink.dev.id == "sim-0"
        finally:
            sink.close()
    with pytest.raises(pysdrlib.err.NoDevice):
        make(server, ident="sim-99")

@pytest.mark.parametrize("bad", ["tcp:/hackrf", "://host:5555", "tcp://", "tcp://host:5555/a/b"])
def test_malformed_targets_fail_clearly(bad):
    from pyspecan.model.sink.live import remote_target
    with pytest.raises(ValueError):
        remote_target(bad)

def test_watching_an_idle_radio_says_how_to_start_it(server):
    sink = make(server).sink
    try:
        with pytest.raises(RuntimeError, match="claim it"):
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
    assert f"-s live -d {short(server)}/sim-0" in text and "--claim" in text and "free" in text and "idle" in text
    assert f"-d {short(server)}/sim\n" in text + "\n" # the type it can open
    assert "attached to this machine" in text
    with pytest.raises(ValueError):
        list_devices("tcp:/bad")

def test_list_cli_flag_prints_and_exits(server, capsys, monkeypatch):
    from pyspecan._internal import main as m
    m._main(m.parse_args(["--list", "-d", server]))
    assert f"{short(server)}/sim-0" in capsys.readouterr().out
    m._main(m.parse_args(["--list", "-d", f"{short(server)}/sim-0"])) # a radio on it: that server's
    assert f"on the server {short(server)}:" in capsys.readouterr().out

def test_a_server_address_alone_picks_a_radio(server, empty_server):
    from pyspecan.model.sink.live import pick_remote
    assert pick_remote(server) == "sim-0"             # the one it hosts, to watch
    assert pick_remote(server, claim=True) == "sim-0" # free, so claimable
    assert pick_remote(empty_server) is None          # hosts none: the server chooses a new radio to open
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

def _dead_address():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return f"tcp://127.0.0.1:{s.getsockname()[1]}" # nothing listens there

def test_known_servers_are_used_when_nothing_is_attached(server, monkeypatch, capsys):
    from pyspecan.model.sink import live
    monkeypatch.setattr(pysdrlib, "find", lambda *a, **k: [])
    monkeypatch.setattr(live, "PROBE_TIMEOUT", 0.5)
    dead = _dead_address()
    sink = GetModel(Sink.LIVE)(device=None, servers=f"{dead}, {server}", claim=True, nfft=256).sink
    try:
        assert sink.remote and sink.server == server and sink.next(2048) # the dead one was skipped
        assert "using sim-0" in capsys.readouterr().out or sink.dev.id == "sim-0"
        targets = [c["target"] for c in sink.radios()]
        assert f"{short(server)}/sim-0" in targets and None in targets # the dead server is listed as not answering
    finally:
        sink.close()
    monkeypatch.setenv("PYSPECAN_SERVERS", server)
    sink = GetModel(Sink.LIVE)(device="auto", nfft=256).sink
    try:
        assert sink.server == server
    finally:
        sink.close()
    monkeypatch.setenv("PYSPECAN_SERVERS", dead)
    with pytest.raises(pysdrlib.err.NoDevice, match=dead):
        GetModel(Sink.LIVE)(device=None, nfft=256)

def test_a_local_radio_comes_before_the_known_servers(server, monkeypatch):
    monkeypatch.setattr(pysdrlib, "find", lambda *a, **k: [pysdrlib.DeviceInfo(driver="sim", label="Simulated radio 0")])
    sink = GetModel(Sink.LIVE)(device=None, servers=server, nfft=256).sink
    try:
        assert not sink.remote
    finally:
        sink.close()

def test_known_servers_must_be_addresses():
    from pyspecan.model.sink.live import parse_servers
    assert parse_servers(" tcp://a:1 ,tcp://b:2/, tcp://a:1") == ["tcp://a:1", "tcp://b:2"]
    assert parse_servers("radiohost a:1") == ["tcp://radiohost:5555", "tcp://a:1"] # as pysdrlib writes them: host[:port]
    assert parse_servers("") == []
    for bad in ("tcp://a:1/sim-0", "radiohost/sim-0", "hackrf@a06"):
        with pytest.raises(ValueError):
            parse_servers(bad)

def test_list_shows_every_known_server(server, empty_server, monkeypatch, capsys):
    from pyspecan._internal import main as m
    from pyspecan.model.sink import live
    monkeypatch.setattr(live, "PROBE_TIMEOUT", 0.5)
    dead = _dead_address()
    m._main(m.parse_args(["--list", "--servers", f"{server},{dead}", "-d", empty_server]))
    out = capsys.readouterr().out
    assert f"{short(server)}/sim-0" in out and f"on the server {short(empty_server)}" in out and f"{short(dead)}: not answering" in out

def test_a_driver_name_and_serial_still_pick_the_radio(monkeypatch):
    seen = []
    real = pysdrlib.open
    monkeypatch.setattr(pysdrlib, "open", lambda what, **k: (seen.append((what, k)), real("sim"))[1])
    sink = GetModel(Sink.LIVE)(device="sim", serial="ABC123", nfft=256).sink
    sink.close()
    assert seen == [("sim", {"serial": "ABC123"})]


# --- controlling a hosted radio from the program --- #
def test_claim_and_release_switch_between_watching_and_controlling(server):
    ctrl = Recorder(make(server))
    try:
        assert ctrl.get_state()["radio"]["control"] == "watching"
        assert ctrl.get_state()["radio"]["can_claim"]
        ctrl.command("claim")
        assert ctrl.get_state()["radio"]["control"] == "controlling"
        ctrl.setting("cf", "100M")
        assert ctrl.sink.get_cf().raw == 100e6
        ctrl.command("release")
        assert ctrl.get_state()["radio"]["control"] == "watching"
        with pytest.raises(ValueError, match="claim"):
            ctrl.setting("cf", "90M")
    finally:
        ctrl.quit()

def test_a_retune_starts_the_plots_over_and_blocks_come_from_the_new_tuning(server):
    ctrl = Recorder(make(server, claim=True))
    try:
        ctrl.command("start")
        assert ctrl.tick()
        ctrl.setting("cf", "123M")
        assert ctrl.source.seq == 0 or ctrl.source._streams == {}
        assert ctrl.tick()
        assert ctrl.sink.get_cf().raw == 123e6
    finally:
        ctrl.quit()

def test_a_radio_retuned_by_its_controller_is_followed_by_a_viewer(server):
    ctrl = Recorder(make(server))
    try:
        owner = pysdrlib.connect(server, "sim-0", claim=True) # the controller, somewhere else
        try:
            if not owner.state["rx"]:
                owner.start_rx()
            owner.set_rx_freq(77e6, flush=True)
            ctrl.command("start")
            assert ctrl.tick()
            assert ctrl.sink.get_cf().raw == 77e6
        finally:
            owner.detach()
    finally:
        ctrl.quit()


# --- the tkGUI of a live sink --- #
def test_tk_shows_who_controls_the_radio_and_disables_tuning_while_watching(server):
    tk = pytest.importorskip("tkinter")
    pytest.importorskip("matplotlib")
    from pyspecan.config import View
    from pyspecan.controller.controller import GetController
    from pyspecan.view.view import GetView
    kw = dict(device=f"{server}/sim-0", nfft=256)
    model = GetModel(Sink.LIVE)(**kw)
    try:
        view = GetView(View.tkGUI, Sink.LIVE)(**kw)
    except tk.TclError:
        pytest.skip("no display")
    ctrl = GetController(View.tkGUI, Sink.LIVE)(model, view, **kw)
    errors = []
    view.root.report_callback_exception = lambda *a: errors.append(a)
    try:
        v = view.sink
        view.root.update()
        assert "Watching" in v.cl_lbl_status.cget("text")
        assert str(view.cl_ent_cf.cget("state")) == "disabled" and str(v.cl_btn_claim.cget("text")) == "Claim"
        ctrl.sink_ui.toggle_control() # Claim
        assert "Controlling" in v.cl_lbl_status.cget("text"), view.tb_lbl_msg.cget("text")
        assert str(view.cl_ent_cf.cget("state")) == "normal" and str(v.cl_btn_claim.cget("text")) == "Release"
        view.cl_var_cf.set("88M")
        ctrl.commit("cf")
        assert ctrl.sink.get_cf().raw == 88e6
        ctrl.sink_ui.toggle_control() # Release
        assert str(view.cl_ent_cf.cget("state")) == "disabled"
    finally:
        ctrl.quit()
    assert not errors, errors


# --- frontends: a converter above the signal mirrors the spectrum, antennas are listed --- #
import json


@pytest.fixture
def frontend_server(tmp_path):
    f = tmp_path / "frontends.json"
    f.write_text(json.dumps({"radio": [{"driver": "sim", "chain": [
        {"direction": "rx", "port": "RX2", "antenna": "ANT500", "lo": 9.75e9, "invert": True, "name": "LNB"}]}]}))
    address, proc = start_server("--frontends", str(f))
    yield address
    proc.terminate()
    proc.communicate(timeout=10)

def test_a_radio_behind_an_inverting_converter_is_flipped_back(frontend_server, monkeypatch):
    sink = GetModel(Sink.LIVE)(device=frontend_server, nfft=256).sink
    try:
        assert sink.inverted and sink.status()["inverted"]
        raw = []
        read = sink.dev.read
        def spy(*a, **k):
            out = read(*a, **k)
            raw.append(out[0].copy())
            return out
        monkeypatch.setattr(sink.dev, "read", spy)
        assert sink.next(2048)
        assert np.array_equal(sink.samples, np.conj(raw[-1])) # mirrored back
        sink.inverted = False
        assert sink.next(2048)
        assert np.array_equal(sink.samples, raw[-1])
    finally:
        sink.close()

def test_a_server_with_no_frontends_is_not_flipped(server):
    sink = make(server).sink
    try:
        assert not sink.inverted and not sink.status()["inverted"]
    finally:
        sink.close()

def test_antennas_are_listed_with_what_is_fitted(frontend_server):
    sink = GetModel(Sink.LIVE)(device=frontend_server, nfft=256).sink
    try:
        ants = sink.antennas()
        assert ants and all({"port", "antenna", "label", "selected", "inverted"} <= a.keys() for a in ants)
        assert any("ANT500" in a["antenna"] and a["inverted"] for a in ants)
        assert sink.status()["antennas"] == ants
    finally:
        sink.close()

def test_antennas_of_a_local_radio():
    sink = GetModel(Sink.LIVE)(device="sim", nfft=256).sink
    try:
        assert isinstance(sink.antennas(), list) # sim has no ports to choose: nothing listed, no error
        assert not sink.inverted
    finally:
        sink.close()

def test_quitting_while_streaming_a_claimed_radio_is_quick_and_frees_it(server):
    c = Recorder(make(server, claim=True))
    c.start_stream()
    c.playing = True
    end = time.monotonic() + 5
    while len(c.ticks) < 3 and time.monotonic() < end:
        time.sleep(0.05)
    assert c.ticks
    t0 = time.monotonic()
    c.quit()
    assert time.monotonic() - t0 < 2.0 and not c.thread.is_alive()
    assert not hosted(server)["sim-0"]["controlled"]
