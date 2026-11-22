# Plots and measurements

Every view lists the plots it can draw, grouped by category ("+ Add plot" in the web view and tkGUI, `types` in the
console). Pointing at one (or at a plot's name, or its grip in tkGUI; `about <type>` in the console) says what data it
uses and what it does to it, what it shows, what to use it for, and roughly what it costs to run (in PSDs, see
[Performance](performance.md)). The web view and tkGUI draw them all, 3D included (drag a 3D plot to turn it, double
click to reset it); the console draws all but 3D.

Every plot, by the category pickers list it under (*italic*: with RPPS, see [DSP plots](dsp.md)):

| Category | Plots |
|---|---|
| Spectrum | PSD, Persistence, FFT, Sweep |
| Time-frequency | Spectrogram, RT Spectrogram, 3D Spectrogram, Surface Spectrogram, Scalogram |
| Time domain | IQ, IQ 3D, PMF, Phasor, IQ Density, Scope, Autocorrelation |
| Measurements | CCDF, Power vs Time, Occupancy, Marker Trend, Phase Noise |
| Analog demodulation | Frequency vs Time, *Analog Demod* |
| Digital demodulation | *Constellation*, *Vector Diagram*, *Constellation Density*, *3D Constellation*, *Eye Diagram*, *Symbol Table* |
| Modulation quality | *Error Vector*, *Error Vector Spectrum* |
| Channel and signal analysis | *Network Analyzer*, *Impulse Response*, *Cyclic Spectrum*, *Waveform ID*, *Hopping*, *Bursts* |
| Decoding | *Signal Profile*, *Frame Raster*, *Decode* |

## Spectrum

- PSD: four analyzer traces, each clear/write, average, max hold, min hold, view or blank, a marker trace, detector, a
  stored reference trace and trace math ("store ref" and the `math` setting, live - ref on its own axis).
- Persistence, FFT.
- With a live radio, Sweep: a span wider than the sample rate. The radio is stepped across `start` to `stop`, the
  middle 80% of each step kept and joined into one trace with the PSD's traces and markers, then tuned back. Heavy:
  raise its "Update every" to keep the rest of a layout live.

## Time-frequency

Spectrogram, RT Spectrogram, 3D Spectrogram (a waterfall of lines), Surface Spectrogram (the spectrogram as a solid
surface colored by level), Scalogram (a wavelet transform: frequency on a log axis against time, sharp in time at high
frequencies, in frequency at low ones).

## Time domain

IQ, IQ 3D, PMF, Phasor, IQ Density, and Scope.

The Scope is an oscilloscope: samples against time, with a trigger (auto, normal, single) and up to `overlay`
triggered sweeps from each block drawn together. `roll` mode is an untriggered strip chart that shows every sample as
a min/max envelope.

- `--plot "scope time_div=10u trig_mode=roll trig_level=0.2"` sets its initial values.
- Screens longer than one block are filled across blocks.
- For faster updates, lower the samples per block and the frame interval together, e.g. `-st 20 --show 20` (about 50
  updates/s). Faster than the screen can redraw only adds lag.

## Measurements and analog demodulation

- Measurements: CCDF, Power vs Time, Occupancy, Phase Noise (L(f) on a log offset axis, integrated phase noise and
  jitter).
- Analog demodulation: Frequency vs Time; with RPPS, Analog Demod (`mode` AM / FM / PM / USB / LSB against time and its
  spectrum, depth / deviation, the carrier offset, and the modulating tone and SINAD when one tone carries it).
- Digital demodulation, modulation quality, channel and signal analysis: with RPPS, see [DSP plots](dsp.md).

## Markers

Markers go on any spectrum (`+ Marker`, or `marker=<kind>` in a layout):

| Kind | What it does |
|---|---|
| point | a fixed frequency |
| peak | lands on the highest peak and stays there; ▲ prev / ▼ next step up / down the peaks by level, ◀ left / ▶ right to the nearest peak in frequency (console: `marker <id> act <marker> next`); `track` follows the peak instead; a threshold line to drag |
| delta | the difference to another marker |
| peaks | a peak table |
| channel power, ACPR | the power in a band, and in its adjacent channels |
| OBW | occupied bandwidth, and the -x dB bandwidth |
| harmonics | dBc of each harmonic, and THD |
| TOI | third order intercept from two tones |
| limit | a line to drag, pass / fail with the margin |
| signals | with RPPS: every signal found, see [DSP plots](dsp.md) |

## Export

Every plot can save its latest frame: its traces as CSV (one row a point: axis, trace, x, y, and z in 3D), its marker
table as CSV, all of it as JSON, or a picture.

- Web: the ⤓ menu in a plot's header (the picture is the canvas as PNG).
- tkGUI: "Export" in its settings (the figure as PNG).
- Console: `export <id> csv|table|json|txt <file>` (txt is the drawing as text).
- Python: `pyspecan.plots.export.FORMATS[what](frame)`, as [the quickstart](library.md) does.

## Update rate

Every plot has "Update every" (blocks): a heavy one (see [Performance](performance.md)) set to 4 renders every 4th
block and skips the blocks in between, so the rest of a layout stays live. A change while stopped still redraws it at
once.
