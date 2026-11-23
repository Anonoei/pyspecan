# Layouts

Start with specific plots, in rows, with their settings, links and markers. `--plot` adds a plot to the current row,
`--row` starts a new one. A plot is its name (case and spaces don't matter) then `key=value` settings; `link=<name>`
links plots that share a name, `marker=<kind>[:key=value,...]` adds a marker.

```
python3 -m pyspecan -v web -f <file> -F cf32 -fs 250k --cal_db -10 \
    --plot "PSD vbw=5 unit=dBm link=a marker=peak" --plot "spectrogram link=a" \
    --row --plot "persistence show_max=on" --plot "scope trig_mode=roll time_div=10u"
```

Every view can save its current layout (web and tkGUI: "Save layout", console: `save <file>`) as JSON, and load one
back ("Load layout", `load <file>`). Launch with it using `--layout <file>`:

```json
--8<-- "examples/layout.json"
```

Settings left out keep their defaults. Linked plots take the first one's shared (level, processing) values, and
`globals` (calibration, the DSP analysis settings) apply to every plot; a global flag given on the command line
(`--cal_db`) wins over the layout's.

## From Python

The same layout from the file and from `--plot` / `--row` items, applied to a `PlotSet` and saved back:

```python
--8<-- "examples/layout.py"
```

The format is [`pyspecan.plots.layout`](../api/plots.md#pyspecan.plots.layout).
