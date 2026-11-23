"""Layouts: the same plots from a JSON file and from --plot / --row items, applied and saved back

    python examples/layout.py

`examples/layout.json` is what "Save layout" writes and `--layout` reads. Settings left out keep their defaults; linked
plots (`link`) share their level and processing settings, and `globals` (calibration) apply to every plot.
"""
import pathlib

from pyspecan.plots import PlotSet, Source, layout, layout_from_kwargs

HERE = pathlib.Path(__file__).resolve().parent

class NoModel:
    """Applying a layout reads nothing: a stand-in model is enough to build the plots"""
    samples = None
    def get_fs(self): raise RuntimeError("not read")

def main():
    from_file = layout_from_kwargs({"layout": str(HERE / "layout.json")})
    from_items = layout_from_kwargs({"layout_items": [ # as the command line gives them
        "PSD vbw=5 link=a marker=peak", "Spectrogram link=a", None, "Persistence show_max=on"], "cal_db": -10})

    for name, spec in (("file", from_file), ("items", from_items)):
        rows = [[p.type for p in row] for row in spec.rows]
        print(f"{name:5}: {rows} globals={spec.globals}")
    assert [[p.type for p in r] for r in from_file.rows] == [[p.type for p in r] for r in from_items.rows]

    plots = PlotSet(Source(NoModel()))
    plots.apply(from_file)
    psd = next(p for _, p in plots if p.NAME == "PSD") # (plot id, plot)
    assert psd.vbw == 5 and psd.cal_db == -10 # its own setting, and the global one
    print(layout.dumps(plots.to_spec()))      # what "Save layout" would write

if __name__ == "__main__":
    main()
