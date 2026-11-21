"""Launch layouts: --plot/--row, json files, PlotSet.apply / to_spec"""
import json

import pytest

from pyspecan.plots import PlotSet, Source, layout, layout_from_kwargs
from pyspecan.plots.layout import LayoutSpec, PlotSpec
from test_plots import FakeModel


def _plots():
    return PlotSet(Source(FakeModel(nfft=1024)))

# --- names and inline specs --- #
@pytest.mark.parametrize("given, name", [
    ("psd", "PSD"), ("power_vs_time", "Power vs Time"), ("Power vs Time", "Power vs Time"),
    ("rt spectrogram", "RT Spectrogram"), ("IQ-3D", "IQ 3D"),
])
def test_plot_names_ignore_case_spaces_and_underscores(given, name):
    assert layout.resolve_type(given) == name

def test_unknown_plot_name_lists_the_choices():
    with pytest.raises(ValueError, match="Spectrogram"):
        layout.resolve_type("spectrum")

def test_inline_rows_settings_links_and_markers():
    spec = layout.parse_inline([
        "PSD vbw=5 unit=dBm link=a marker=peak marker=channel:freq=1M,bw=200k", "spectrogram link=a", None,
        "Power vs Time history=50",
    ])
    assert [[p.type for p in row] for row in spec.rows] == [["PSD", "Spectrogram"], ["Power vs Time"]]
    psd = spec.rows[0][0]
    assert psd.settings == {"vbw": "5", "unit": "dBm"} and psd.link == "a"
    assert psd.markers == [{"kind": "peak"}, {"kind": "channel", "freq": "1M", "bw": "200k"}]
    assert spec.rows[1][0].settings == {"history": "50"}

def test_inline_extra_and_leading_row_breaks_make_no_empty_rows():
    spec = layout.parse_inline([None, "PSD", None, None, "FFT", None])
    assert [[p.type for p in r] for r in spec.rows] == [["PSD"], ["FFT"]]

def test_inline_name_after_settings_is_an_error():
    with pytest.raises(ValueError, match="name has to come before"):
        layout.parse_plot("PSD vbw=5 extra")

# --- json --- #
def test_json_round_trip():
    spec = LayoutSpec([[PlotSpec("PSD", {"vbw": 5}, "a", [{"kind": "peak", "rank": 2}]), PlotSpec("Spectrogram", link="a")],
                       [PlotSpec("Persistence", {"show_max": True})]], {"cal_db": -10.0})
    text = layout.dumps(spec)
    assert json.loads(text)["globals"] == {"cal_db": -10.0}
    assert layout.loads(text) == spec

@pytest.mark.parametrize("doc, match", [
    ('{"rows": [[{"type": "PSD"}]], "plots": []}', "unknown layout key"),
    ('{"rows": [[{"type": "PSD", "vbw": 5}]]}', "unknown key"),
    ('{"rows": [[{"settings": {}}]]}', "\"type\""),
    ('{"rows": [[{"type": "PSD", "markers": [{"rank": 1}]}]]}', "\"kind\""),
    ('{"rows": [', "not valid json"),
])
def test_json_shape_errors(doc, match):
    with pytest.raises(ValueError, match=match):
        layout.loads(doc)

# --- validation --- #
@pytest.mark.parametrize("spec, match", [
    (LayoutSpec([]), "no plots"),
    (LayoutSpec([[PlotSpec("PSD", {"nope": 1})]]), "no setting 'nope'"),
    (LayoutSpec([[PlotSpec("PSD", {"window": "square"})]]), "row 1, plot 1 \\(PSD\\): Window"),
    (LayoutSpec([[PlotSpec("PSD", {"cal_db": 3})]]), "globals"),
    (LayoutSpec([[PlotSpec("PSD")]], {"vbw": 3}), "unknown global setting"),
    (LayoutSpec([[PlotSpec("PSD", link="a"), PlotSpec("Scope", link="a")]]), "can not be linked"),
    (LayoutSpec([[PlotSpec("PSD", link="a")], [PlotSpec("FFT", link="a")]]), "row 2, plot 1 \\(FFT\\)"),
    (LayoutSpec([[PlotSpec("CCDF", markers=[{"kind": "peak"}])]]), "markers"),
    (LayoutSpec([[PlotSpec("PSD", markers=[{"kind": "peak", "bw": "1M"}])]]), "no setting 'bw'"),
    (LayoutSpec([[PlotSpec("PSD", markers=[{"kind": "laser"}])]]), "marker kind"),
])
def test_validation_names_what_is_wrong(spec, match):
    with pytest.raises(ValueError, match=match):
        layout.validate(spec)

def test_validation_against_what_a_view_can_draw():
    with pytest.raises(ValueError, match="can not draw"):
        layout.validate(LayoutSpec([[PlotSpec("IQ 3D")]]), plot_types=["PSD"])

# --- plotset --- #
def test_apply_builds_rows_settings_links_and_markers():
    plots = _plots()
    plots.apply(layout.parse_inline(["PSD vbw=5 link=a marker=peak", "Spectrogram link=a", None, "Persistence show_max=on"]))
    (a, b), (c,) = plots.layout
    pa, pb, pc = plots.get(a), plots.get(b), plots.get(c)
    assert (pa.NAME, pb.NAME, pc.NAME) == ("PSD", "Spectrogram", "Persistence")
    assert pa.link is pb.link and pa.link is not None and pc.link is None
    assert pb.vbw == 5.0             # link values come from the first member
    assert pc.show_max is True
    assert len(pa.markers) == 1 and pa.markers is pb.markers # one shared set

def test_apply_replaces_plots_and_resets_globals():
    plots = _plots()
    plots.apply(LayoutSpec([[PlotSpec("PSD")]], {"cal_db": -10}))
    shared = plots.globals
    old = next(iter(plots.plots))
    plots.apply(LayoutSpec([[PlotSpec("FFT")]]))
    assert [p.NAME for _, p in plots] == ["FFT"]
    assert old not in plots.plots     # fresh ids
    assert plots.globals is shared and plots.globals["cal_db"] == 0.0

def test_apply_is_all_or_nothing():
    plots = _plots()
    plots.apply(LayoutSpec([[PlotSpec("PSD")]]))
    before = dict(plots.plots)
    with pytest.raises(ValueError):
        plots.apply(LayoutSpec([[PlotSpec("FFT")], [PlotSpec("PSD", {"vbw": -1})]]))
    assert plots.plots == before

def test_to_spec_round_trips_and_keeps_only_changes():
    spec = layout.parse_inline(["PSD vbw=5 link=a marker=peak marker=delta:ref=M1", "Spectrogram link=a", None,
                                "Persistence show_max=on", "Scope trig_mode=roll"])
    spec.globals = {"ext_gain": 3.0}
    plots = _plots()
    plots.apply(spec)
    out = plots.to_spec()
    assert out.globals == {"ext_gain": 3.0}
    psd, spg = out.rows[0]
    assert psd.settings == {"vbw": 5.0} and psd.link == spg.link == "link1"
    assert [m["kind"] for m in psd.markers] == ["peak", "delta"] and spg.markers == [] # shared markers written once
    assert out.rows[1][0].settings == {"show_max": True} and out.rows[1][1].settings == {"trig_mode": "roll"}

    again = _plots()
    again.apply(layout.loads(layout.dumps(out)))
    assert again.to_spec() == out

# --- launch --- #
def test_launch_layout_sources():
    assert layout_from_kwargs({}) == layout.default()
    spec = layout_from_kwargs({"layout_items": ["FFT"], "cal_db": -3.0})
    assert spec.rows[0][0].type == "FFT" and spec.globals == {"cal_db": -3.0}
    with pytest.raises(ValueError, match="either"):
        layout_from_kwargs({"layout_items": ["FFT"], "layout": "x.json"})

def test_launch_from_file_with_global_flag_override(tmp_path):
    path = tmp_path / "l.json"
    path.write_text(layout.dumps(LayoutSpec([[PlotSpec("PSD")]], {"cal_db": -10.0, "ext_gain": 2.0})))
    spec = layout_from_kwargs({"layout": str(path), "cal_db": 1.0})
    assert spec.globals == {"cal_db": 1.0, "ext_gain": 2.0}
