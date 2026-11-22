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

@pytest.mark.parametrize("given, view", [("tk", "tkGUI"), ("TKGUI", "tkGUI"), ("tkGUI", "tkGUI"), ("c", "CUI"), ("Web", "WEB")])
def test_view_names_ignore_case(given, view):
    assert m.parse_args(["-v", given]).view == view

def test_short_choices_in_help(capsys):
    with pytest.raises(SystemExit):
        m.parse_args(["-h"])
    out = capsys.readouterr().out
    assert "{cui,tk,web}" in out and "{file,live,tcpiq}" in out

def test_file_format_is_capital_f_and_d_is_the_radio():
    assert m.parse_args(["-F", "ci16t"]).fmt == "ci16t"
    assert m.parse_args(["-s", "live", "-d", "uhd"]).device == "uhd"
    with pytest.raises(SystemExit):
        m.parse_args(["-d", "cf64"]) # file sink: no -d any more

def test_file_format_takes_pysdrlibs_other_spellings(capsys):
    assert m.parse_args(["-F", "ci16"]).fmt == "ci16t" # pysdrlib's alias, named as -h lists it
    with pytest.raises(SystemExit):
        m.parse_args(["-F", "cs16"])
    assert "one of ci4t" in capsys.readouterr().err

def test_each_layer_gets_only_its_options():
    from pyspecan.arguments import split
    _importable(View.WEB)
    part = split(View.WEB, Sink.TCPIQ, {"tcp_port": 1, "nfft": 512, "port": 8080, "show": 20.0, "cal_db": -3.0})
    assert part["model"] == {"tcp_port": 1, "nfft": 512}
    assert part["ui"] == {"port": 8080, "show": 20.0}
    assert part["plots"] == {"cal_db": -3.0}

def test_unknown_options_are_rejected():
    from pyspecan.arguments import split
    with pytest.raises(TypeError, match="port"): # a web option, not the console's
        split(View.CUI, Sink.FILE, {"port": 8080})

def test_specan_checks_names_and_options_before_opening_anything():
    from pyspecan import SpecAn, err
    with pytest.raises(err.UnknownOption):
        SpecAn("nope")
    with pytest.raises(TypeError, match="vbw"):
        SpecAn("cui", "file", vbw=3)
    with pytest.raises(ValueError, match="Laser"):
        SpecAn("cui", "FILE", layout_items=["Laser"])

@pytest.mark.parametrize("argv, note", [
    (["-v", "cui", "-d", "cf64"], "the file format is -F"),
    (["-v", "cui", "--vbw", "3"], "--plot \"PSD vbw=...\""),
    (["-v", "cui", "-s", "tcpiq", "--port", "1"], "--tcp_port"),
])
def test_moved_options_say_what_to_use(argv, note, capsys):
    with pytest.raises(SystemExit):
        m.parse_args(argv)
    assert note in capsys.readouterr().err

def test_web_keeps_its_own_host_and_port_with_tcpiq():
    from pyspecan.arguments import hint
    assert hint("port", View.WEB, Sink.TCPIQ) is None
    assert hint("listen", View.WEB, Sink.TCPIQ) == "the TCP IQ option is --tcp_listen"

def test_specan_says_what_to_use_for_moved_options():
    from pyspecan import SpecAn
    with pytest.raises(TypeError, match="tcp_host"):
        SpecAn("cui", "tcpiq", host="x")
