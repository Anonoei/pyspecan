# AGENTS.md

Orientation for agents working in this repository. Read this first; it says where everything else is.

pyspecan is a spectrum analyzer in Python (numpy): samples from a file, a radio (pysdrlib, local or on a server) or a
TCP IQ stream, read one block per tick and drawn by a web (FastAPI + a canvas page), tk (matplotlib) or console (text)
view as any number of plots: spectra, spectrograms, time domain, measurements, markers, and with the optional rpps
library signal search, demodulation, modulation quality, channel analysis and decoding. Plots are toolkit independent:
every view draws the same frames.

## Commands

```
python tools/builder.py -s            # pip install -e ".[dev]"
python -m pytest -q                   # the suite; Linux without a display: xvfb-run -a python -m pytest -q
PYSPECAN_NO_RPPS=1 python -m pytest -q  # without the DSP plots (rpps is optional)
ruff check src tests tools examples
python tools/builder.py -d            # docs: API pages + llms files (tools/gen_docs.py), then zensical build --strict
python -m pyspecan -v web|tk|cui -s file|live|tcpiq -h   # the options of a view and sink
python tools/benchmark.py [--plots a,b] # each plot's cost in PSDs
python tools/screenshots.py           # media/*.png (playwright chromium, a display, pillow)
```

The browser tests (`tests/test_web_*.py`) skip without playwright and a chromium (`python -m playwright install
chromium`): check they ran.

## The model in one screen

```
sink -> Model -> Source -> Plot.update() -> Frame -> Controller -> view
file, live,  one block   FFT frame Streams    a plot renders   what to draw,   owns playback,   web, tk,
tcpiq        per tick    (swept, rt), shared  the source       not how         the plots        console
```

- `Model` (`pyspecan.model`) holds a sink; `get_block_size()` is how many samples a tick reads (`-st` ms, within
  `--min_fft` / `--max_fft` realtime frames and `--block_max`). Sinks set `contiguous` False after lost samples.
- `Source` (`plots.source`): the block, and `Stream`s that cut it into FFT frames (swept: hop nfft; rt: overlapped),
  carrying leftover samples across blocks, shared by plots asking for the same (mode, nfft, window).
- `Plot` (`plots.base`): `SETTINGS` (`Setting`: own, link or global scope; read back as attributes), `FEATURES` (what a
  view must draw), `CATEGORY`, `ABOUT` (what pickers say, with the cost in PSDs), `render() -> Frame | None`,
  registered with `@plot("Name")`. Spectrum plots subclass `FreqPlot` and carry `markers` (`MarkerKind`,
  `@marker_kind("name")`).
- `Frame` (`plots.frame`): axes, traces, images, surfaces, marks, bands, a table, a readout. Nothing about how.
- `PlotSet` (`plots.plotset`): a view's plots by id (`p1`...), rows, links, global settings; `update()` renders them.
  `LayoutSpec` (`plots.layout`) is what `--plot` / `--row` / `--layout` give and "Save layout" writes.
- `Controller` (`controller.base`): owns model, source and plot set, `step()` = read, tick, render, `deliver(frames,
  status)` to the view; threaded playback (web, tk) or `tick()` from the view (console). Holds `lock` for any change.
- `SpecAn` (`pyspecan.specan`) builds model, view and controller from options; `arguments` gives each layer
  (`model`, `ui`, `plots`) only its own options.

Full picture: the `pyspecan` and `pyspecan.plots` docstrings.

## Where things are

| Path | What |
|---|---|
| `src/pyspecan/<pkg>/__init__.py` | **the package's documentation** (its docstring), rendered in the API reference |
| `src/pyspecan/model/` | `Model`, sinks (`sink/file.py`, `live.py`, `tcpiq.py`) |
| `src/pyspecan/plots/` | every plot (`psd`, `spg`, `pst`, `fft`, `iq`, `scope`, `measure`, `analog`, `timefreq`, `sweep`), `markers`, `settings`, `layout`, `export` |
| `src/pyspecan/plots/dsp/` | plots on rpps: `analyzer` (shared search and lock), `signals`, `analog`, `demod`, `quality`, `channel`, `decode` |
| `src/pyspecan/measure/` | numpy-only measurement math |
| `src/pyspecan/controller/`, `view/` | `CUI`, `WEB` (`wire.py`: binary frame messages; `static/app.js`: the page), `tkGUI` |
| `examples/` | self-checking scripts; the guides embed them; `tests/test_examples.py` runs them |
| `docs/` | the site: guides (`docs/guide/`), gallery, examples index, contributing; `docs/api/` and `docs/llms*.txt` are generated |
| `tests/` | the suite, flat; `conftest.py` puts `src/` on the path |
| `tools/` | builder, docs generator, benchmark, screenshots (and `demo.py`, their synthetic capture) |

Imports run down the data path: `measure` knows nothing of plots; plots and the model import no view, controller or
GUI library; only `plots/dsp/` imports rpps, inside the calls (`plots.settings.HAVE_RPPS` finds it without importing).

## Where to read more

| Question | Read |
|---|---|
| What package X holds, and its rules | `src/pyspecan/X/__init__.py` docstring |
| How plots, settings, links, markers and layouts work | `pyspecan.plots`, then `plots.base`, `plots.settings`, `plots.plotset`, `plots.layout` |
| How frames reach the browser | `pyspecan.controller.WEB.wire` |
| The DSP plots' shared search and lock | `pyspecan.plots.dsp`, `plots.dsp.analyzer` |
| Command line options, and who gets which | `pyspecan.arguments` |
| How to use it for a task | `docs/guide/*.md` |
| Setup, testing, CI, releases | `docs/contributing.md` |
| Everything at once | `docs/llms-full.txt` (after `python tools/gen_docs.py`) |

## Conventions

- **Plots never touch a toolkit**, views only draw frames; a new kind of drawing goes into `plots.frame` and every view.
- **Each layer gets only its own options** (`pyspecan.arguments`).
- **rpps is optional:** run the suite with and without `PYSPECAN_NO_RPPS=1` when touching plots.
- **I/O through pysdrlib:** formats, radios, servers, TCP IQ. A bug there is fixed in pysdrlib.
- **A new plot's `ABOUT.cost`** comes from `tools/benchmark.py`; the benchmark flags a cost more than twice off.
- **No aliases:** a rename or move drops the old name and fixes the callers.
- **Failures are never silent:** report them to the view's status and stderr (`Controller.report_error`).
- **Docs live with what they describe:** concepts in the package / module docstring, usage in a guide that embeds an
  example script. Python blocks in README.md and `docs/` run in `tests/test_docs.py` (mark untestable ones
  `# docs: skip`).
- Branch from `dev`; `main` is released.
