# pyspecan
 A spectrum analyzer library

 - [Documentation](https://anonoei.github.io/pyspecan/)
 - [PyPI](https://pypi.org/project/pyspecan/)


# Examples
tkGUI, PSD and spectrogram
![tkGUI_Swept](/media/SWEPT_tkGUI.png)
![tkGUI_Swept](/media/SWEPT_tkGUI2.png)

tkGUI, persistence and realtime spectrogram
![tkGUI_RT](/media/RT_tkGUI.png)
![tkGUI_RT](/media/RT_tkGUI2.png)

# Usage
- View (-v|--view): specifies which frontend to use (tk, web, cui; any case)
- Sink (-s|--sink): specifies which interface to use (file, live, tcpiq)
  - Live uses [pysdrlib](https://github.com/anonoei/pysdrlib) for hardware SDR abstractions
    - `-d` picks the radio: a driver (`uhd`), or a radio on a pysdrlib server (`tcp://host:5555/hackrf-0`). With no `-d` it uses the first radio attached to this machine
    - `--servers tcp://a:5555,tcp://b:5555` (or the `PYSPECAN_SERVERS` environment variable) names known servers. With no `-d` and no radio attached here, it uses the first server that has one. `--list` and the radio picker show their radios too
    - `--list` prints every radio it can use, with the options that pick each one
  - TCPIQ takes `--tcp_host`, `--tcp_port`, `--tcp_listen`, `--tcp_timeout`

## Module
- `python3 -m pyspecan --help`
- tkGUI, file: `python3 -m pyspecan`
- tkGUI, live (hackrf): `python3 -m pyspecan -s live -d hackrf`
- web, file: `python3 -m pyspecan -v web -f <file> -F cf64 -fs 250k`, then open http://127.0.0.1:8000
- console, file: `python3 -m pyspecan -v cui -f <file> -F cf64 -fs 250k`, type `help` (draws plots as text, needs no plotting library)

## Layouts
Start with specific plots, in rows, with their settings, links and markers. `--plot` adds a plot to the
current row, `--row` starts a new one. A plot is its name (case and spaces don't matter) then `key=value`
settings; `link=<name>` links plots that share a name, `marker=<kind>[:key=value,...]` adds a marker.
```
python3 -m pyspecan -v web -f <file> -F cf64 -fs 250k --cal_db -10 \
    --plot "PSD vbw=5 unit=dBm link=a marker=peak" --plot "spectrogram link=a" \
    --row --plot "persistence show_max=on" --plot "scope trig_mode=roll time_div=10u"
```
Every view can save its current layout (web and tkGUI: "Save layout", console: `save <file>`) as json, and
load one back ("Load layout", `load <file>`). Launch with it using `--layout <file>`:
```json
{"globals": {"cal_db": -10},
 "rows": [
   [{"type": "PSD", "link": "a", "settings": {"vbw": 5}, "markers": [{"kind": "peak"}]},
    {"type": "Spectrogram", "link": "a"}],
   [{"type": "Persistence", "settings": {"show_max": true}}]]}
```
Settings left out keep their defaults. Linked plots take the first one's shared (level, processing) values.

## Scope
The "Scope" plot is an oscilloscope: samples against time, with a trigger (auto, normal, single) and up
to `overlay` triggered sweeps from each block drawn together. `roll` mode is an untriggered strip chart
that shows every sample as a min/max envelope.
- `--plot "scope time_div=10u trig_mode=roll trig_level=0.2"` sets its initial values
- Screens longer than one block are filled across blocks
- For faster updates, lower the samples per block and the frame interval together, e.g. `-st 20 --show 20` (about 50 updates/s). Faster than the screen can redraw only adds lag.

## Plot extensions
Other packages can add plots and marker kinds, which every view then lists. Name a module that
registers them (`@plot("Name")`, `@marker_kind("name")`) under the `pyspecan.plots` entry point group:
```toml
[project.entry-points."pyspecan.plots"]
mypkg = "mypkg.specan_plots"
```
See the `pyspecan.plots` docstring for a full example. `PYSPECAN_NO_EXTENSIONS=1` turns them off.

# Install
1. Run `pip install pyspecan`, to install
2. Run `python3 -m pyspecan --help` to view available arguments

# Contributing
1. `git clone https://github.com/Anonoei/pyspecan`
2. `cd pyspecan`
3. `git branch -c feature/<your feature>`
4. `python3 builder.py -b -l` build and install locally

## Build executable
1. `pyinstaller src/pyspecan.spec`
2. `./dist/pyspecan`
