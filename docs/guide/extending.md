# Extending

Plots and marker kinds register by name, and every view (web, tk, console) then lists them in its pickers, draws them
from their frames, saves them in layouts and accepts them in `--plot`.

## A plot and a marker kind

A plot subclasses `Plot`, declares its `SETTINGS` (read back as attributes), what a view must draw to offer it
(`FEATURES`), where the picker lists it (`CATEGORY`) and what the picker says about it (`ABOUT`, with its cost in PSDs:
measure it with [the benchmark](performance.md)), and returns a `Frame` from `render()`. A marker kind subclasses
`MarkerKind` and returns a `Result` (table rows, and marks or bands to draw) from `evaluate()`:

```python
--8<-- "examples/extension.py"
```

Spectrum plots that carry markers subclass `FreqPlot` (`pyspecan.plots.freq`), which gives them the PSD's traces,
detector, averaging, units and markers.

## In pyspecan

Put the plot in a module of `src/pyspecan/plots/` and import it in `plots/__init__.py` (the import order is the order
pickers list plots in); marker kinds go in `plots/markers.py`; math on arrays that is not about plots goes in
`pyspecan.measure`. Plots on rpps go in `plots/dsp/` and import rpps inside the call, so pyspecan still imports and
runs without it. Then:

- `tests/test_plots.py` for what it computes; `tests/test_web_all.py` draws every registered plot and marker kind in a
  real browser.
- Its `ABOUT.cost` from `python dev/benchmark.py --plots <name>` (the benchmark flags a cost more than twice off).

## From another package

Name a module that registers them under the `pyspecan.plots` entry point group, and pyspecan imports it at start:

```toml
[project.entry-points."pyspecan.plots"]
mypkg = "mypkg.specan_plots"
```

Extensions load after the built in plots (so pickers list them last), in entry point name order. One that fails to
import, or registers a name already taken, logs a warning (what it registered before failing stays).
`PYSPECAN_NO_EXTENSIONS=1` loads none. A layout naming a plot from an extension that is not installed says so.
