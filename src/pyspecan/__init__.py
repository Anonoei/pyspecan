"""pyspecan: a spectrum analyzer library

Samples from a file, a radio (through pysdrlib) or a TCP IQ stream are read one block per tick and drawn by a web,
tk or console view as any number of plots: spectra, spectrograms, time domain, measurements, and with the optional
rpps library the analysed signal's constellation, eye diagram, link response and decoded messages. Run it as a program
(`python -m pyspecan`, or the `pyspecan` / `pyspecan-cui` scripts) or from Python (`SpecAn`, or the plots on their own,
without a view). How to use it is in the guides of the documentation site (https://anonoei.github.io/pyspecan/).

## The data path

```
sink -> Model -> Source -> Plot.update() -> Frame -> Controller -> view
file, live,      one block    shared FFT frames    a plot turns the source    what to draw,   owns playback,   web, tk,
tcpiq            per tick     (Stream: swept, rt)  into a Frame               not how         the plots        console
```

- `model`: a `Model` holds a sink and decides how many samples one tick reads (`Model.get_block_size`).
- `plots`: `Source` is what every plot reads, the block and FFT frame streams shared between plots; `Plot` subclasses
  registered with `@plot("Name")` turn it into a `Frame`; a `PlotSet` is the live plots of a view, their rows, links
  and global settings, built from a `LayoutSpec`.
- `controller`: `Controller` owns the model, the source and the plot set, steps playback and hands each tick's frames
  to its view (`deliver`). It is view independent; each view subclasses it.
- `view`: the frontends. The web view (FastAPI, a browser over a websocket), tkGUI (matplotlib in tk) and the console
  (text) draw the same frames.

## Where things are

| Package | What is in it |
|---|---|
| `pyspecan.specan` | `SpecAn`: build the model, view and controller from options, and run |
| `pyspecan.arguments` | the command line: which options exist, and which layer each belongs to (`LAYERS`) |
| `pyspecan.config` | `View` and `Sink` (the frontends and sample sources by name), developer toggles |
| `pyspecan.model` | `Model` and the sinks: `SinkFile`, `SinkLive` (pysdrlib radios, recording), `SinkTcpIq` |
| `pyspecan.plots` | toolkit independent plots: `Source`, `Plot`, `Frame`, `PlotSet`, layouts, markers, settings, export |
| `pyspecan.plots.dsp` | plots on rpps (`pip install pyspecan[dsp]`): signal search, demodulation, quality, channel, decode |
| `pyspecan.measure` | spectrum measurement math, numpy only: averaging, detectors, peaks, channel power, CCDF, units |
| `pyspecan.controller` | `Controller` (view independent) and the web, tk and console controllers |
| `pyspecan.view` | the windows / pages / terminal each frontend draws in |
| `pyspecan.backend` | matplotlib (no pyplot) and tk helpers for tkGUI |
| `pyspecan.obj`, `pyspecan.utils` | `Frequency`; argument helpers, registries, PMFs, profiling |

Imports run down the data path: `measure` knows nothing of plots, plots and the model know nothing of views or
toolkits, and only `controller` and `view` import a GUI library (each only for its own view). The model never sees a
view's options nor a view the sink's (`pyspecan.arguments`).

## Extending

Plots and marker kinds register by name, and every view lists the ones it can draw. Another package adds its own
through the `pyspecan.plots` entry point group (see `pyspecan.plots`); `PYSPECAN_NO_EXTENSIONS=1` loads none. Without
rpps (or with `PYSPECAN_NO_RPPS=1`) the DSP plots are not registered and everything else works the same.
"""

__version__ = "0.7.1"
__author__ = "Anonoei <to+dev@an0.us>"

from . import _internal, err, obj, utils
from .config import View, config

# from .model.base import Model
from .model.base import Model
from .model.model import GetModel
from .specan import SpecAn
