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

## Plots and measurements
Every view lists the plots it can draw (the web view and tkGUI draw them all, 3D included: drag a 3D plot to turn it,
double click to reset it; the console draws all but 3D).
- Spectrum: PSD (max / min hold, averaging, detector), Spectrogram, RT Spectrogram, 3D Spectrogram, Persistence, FFT
- Time domain: IQ, IQ 3D, PMF, Phasor, IQ Density, Scope (triggered / roll), Frequency vs Time
- Measurements: CCDF, Power vs Time, Occupancy, Phase Noise (L(f) on a log offset axis, integrated phase noise and
  jitter), Analog Demod (AM / FM / PM against time and its spectrum, depth / deviation, modulating frequency, SINAD)
- Markers on any spectrum (`+ Marker`, or `marker=<kind>` in a layout): point, peak (with a threshold line to drag),
  delta, peaks (peak table), channel power, ACPR, OBW (and -x dB bandwidth), harmonics (dBc and THD), TOI (third order
  intercept from two tones), limit (a line to drag, pass / fail with the margin), and with RPPS signals (below)

## Scope
The "Scope" plot is an oscilloscope: samples against time, with a trigger (auto, normal, single) and up
to `overlay` triggered sweeps from each block drawn together. `roll` mode is an untriggered strip chart
that shows every sample as a min/max envelope.
- `--plot "scope time_div=10u trig_mode=roll trig_level=0.2"` sets its initial values
- Screens longer than one block are filled across blocks
- For faster updates, lower the samples per block and the frame interval together, e.g. `-st 20 --show 20` (about 50 updates/s). Faster than the screen can redraw only adds lag.

## DSP plots (optional)
With [RPPS](https://github.com/Anonoei/RPPS) installed (`pip install pyspecan[dsp]`), pyspecan finds and analyses signals.
Without it everything else works the same, and these plots are not listed.
- The `signals` marker (any spectrum: PSD, spectrograms, persistence, 3D spectrogram) boxes every signal found in the
  block, with its width, SNR and duty cycle in the marker table. The analysed one is green: click a box to analyse that
  signal, drag a box's edges to adjust it
- "Constellation": the analysed signal's symbols after timing, carrier and gain recovery, over the ideal points, with
  modulation, symbol rate, roll-off, Es/N0, EVM and carrier offset
- "Eye Diagram": its matched filter output over two symbols, I and Q
- "Network Analyzer": the link's frequency response across the signal (magnitude, phase, group delay), measured blind
  from the decided symbols, no stimulus needed; "Impulse Response": the same inverse transformed, echoes by delay and level
- "3D Constellation": I and Q against time, the symbols on the matched filter's path
- "Error Vector": EVM, magnitude and phase error per symbol, with the error summary (peak EVM, MER, IQ offset, gain
  imbalance, quadrature error); "Error Vector Spectrum": where in the band the errors are
- "Cyclic Spectrum": the spectral correlation against cycle frequency and the spectral coherence image, with the symbol
  rate and carrier symmetry found blind (no lock needed)
- "Symbol Table": the decided symbols
- The "Analysis" globals (`--dsp_freq`, `--dsp_bw`, `--dsp_mod`, `--dsp_baud`) pick the signal and, when known, its
  modulation and symbol rate. Blank picks the strongest signal and finds the rest
```
python3 -m pyspecan -v web -f <file> -F cf64 -fs 1M \
    --plot "PSD marker=signals" --plot constellation --row --plot "eye diagram" --plot "network analyzer"
```

## Plot extensions
Other packages can add plots and marker kinds, which every view then lists. Name a module that
registers them (`@plot("Name")`, `@marker_kind("name")`) under the `pyspecan.plots` entry point group:
```toml
[project.entry-points."pyspecan.plots"]
mypkg = "mypkg.specan_plots"
```
See the `pyspecan.plots` docstring for a full example. `PYSPECAN_NO_EXTENSIONS=1` turns them off.

# Install
1. Run `pip install pyspecan`, to install (`pyspecan[tk]`, `[web]`, `[dsp]` for the views and the DSP plots)
2. Run `python3 -m pyspecan --help` to view available arguments

# Contributing
1. `git clone https://github.com/Anonoei/pyspecan`
2. `cd pyspecan`
3. `git branch -c feature/<your feature>`
4. `python3 builder.py -b -l` build and install locally

## Build executable
1. `pyinstaller src/pyspecan.spec`
2. `./dist/pyspecan`
