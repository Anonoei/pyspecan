"""The command line: every view and sink combination builds, and the layout flags"""
import pytest

from pyspecan._internal import main as m
from pyspecan.config import Sink, View

VIEWS = [v for v in View if v != View.NONE]
SINKS = [s for s in Sink if s != Sink.NONE]

def _importable(view):
    try:
        m.build_parser(view, Sink.FILE)
    except ImportError as e: # optional dependency (web, tk) missing
        pytest.skip(f"{view.name}: {e}")

@pytest.mark.parametrize("view", VIEWS, ids=lambda v: v.name)
@pytest.mark.parametrize("sink", SINKS, ids=lambda s: s.name)
def test_every_view_and_sink_builds_without_conflicts(view, sink):
    _importable(view)
    parser = m.build_parser(view, sink) # raises argparse.ArgumentError on a duplicate flag
    dests = [a.dest for a in parser._actions if a.dest != "help"]
    shared = {"layout_items"} # --plot and --row append to it on purpose
    assert len([d for d in dests if d not in shared]) == len({d for d in dests if d not in shared})

@pytest.mark.parametrize("view", VIEWS, ids=lambda v: v.name)
def test_help_exits_cleanly(view, capsys):
    _importable(view)
    with pytest.raises(SystemExit) as e:
        m.parse_args(["-v", view.name, "-h"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert "--plot" in out and "--layout" in out and "--show" in out
    assert "--vbw" not in out

def test_list_defaults_to_the_live_sink():
    assert m.parse_args(["--list"]).sink == Sink.LIVE.name
    assert m.parse_args([]).sink == Sink.FILE.name
    assert m.parse_args(["--list", "-s", "file"]).sink == Sink.FILE.name

def test_tcpiq_and_web_have_separate_ports():
    _importable(View.WEB)
    ns = m.parse_args(["-v", "web", "-s", "tcpiq", "--tcp_port", "4321", "--port", "8080"])
    assert ns.tcp_port == 4321 and ns.port == 8080

def test_plot_and_row_keep_their_order():
    ns = m.parse_args(["-v", "cui", "--plot", "PSD vbw=5", "--plot", "FFT", "--row", "--plot", "Scope", "--cal_db", "-3"])
    assert ns.layout_items == ["PSD vbw=5", "FFT", None, "Scope"]
    assert ns.cal_db == -3.0
