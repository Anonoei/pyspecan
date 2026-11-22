# pyspecan
A spectrum analyzer library: web, tk and console views of samples from files, radios and TCP IQ streams.

- [Documentation](https://anonoei.github.io/pyspecan/): guides, examples and the API reference
- [PyPI](https://pypi.org/project/pyspecan/)
- For AI agents: [AGENTS.md](https://github.com/Anonoei/pyspecan/blob/main/AGENTS.md), and
  [llms-full.txt](https://anonoei.github.io/pyspecan/llms-full.txt) (the whole library in one file)

Web: PSD with found signals and a peak marker, spectrogram, persistence, surface spectrogram
![web spectrum](https://raw.githubusercontent.com/Anonoei/pyspecan/main/media/web_spectrum.png)

Web, with RPPS: the analysed signal's constellation, eye diagram and the link's response (network analyzer)
![web dsp](https://raw.githubusercontent.com/Anonoei/pyspecan/main/media/web_dsp.png)

Console: PSD and spectrogram drawn as text
![console](https://raw.githubusercontent.com/Anonoei/pyspecan/main/media/cui_spectrum.png)

More in the [gallery](https://anonoei.github.io/pyspecan/gallery/).

## Install
```
python3 -m pip install pyspecan          # pyspecan[web], [tk] for those views; [dsp] adds the DSP plots (rpps)
```
The console view needs nothing more. Radios and file formats come from [pysdrlib](https://github.com/anonoei/pysdrlib).

## Usage
```
python3 -m pyspecan -v web -f capture.cf32 -fs 1M          # then open http://127.0.0.1:8000
python3 -m pyspecan -v cui -f capture.cs16 -fs 2M           # the console: type `help`
python3 -m pyspecan -s live -d hackrf                       # tkGUI on a radio
python3 -m pyspecan -v web -f capture.cf32 -fs 1M --plot "PSD marker=peak" --plot spectrogram --row --plot persistence
python3 -m pyspecan --help                                  # every option; -v <view> -s <sink> --help for theirs
```

From Python, the plots run without a view: a file read block by block, a PSD with a peak marker.
```python
import numpy as np
from pyspecan.config import Sink
from pyspecan.model.model import GetModel
from pyspecan.plots import PlotSet, Source, layout

np.exp(2j * np.pi * 125e3 * np.arange(500_000) / 1e6).astype(np.complex64).tofile("tone.cf32") # a capture
model = GetModel(Sink.FILE)(path="tone.cf32", fmt="cf32", Fs=1e6)
source = Source(model)
plots = PlotSet(source)
plots.apply(layout.parse_inline(["PSD marker=peak", "Spectrogram"]))
while model.sink.next(model.get_block_size()):  # one block a tick, as a view plays it
    source.tick(model.sink.contiguous)
    frames = plots.update()                      # {plot id: Frame}: what views draw
print(frames["p1"].table.rows[0].cells)         # ['M1', 'peak', '125 kHz', '-32.27 dB/Hz']
```
`SpecAn("web", "file", path="tone.cf32", Fs="1M", layout_items=["PSD marker=peak"])` opens the same in a view.

## Learn more
| | |
|---|---|
| [Guides](https://anonoei.github.io/pyspecan/guide/sources/) | sources (files, radios, TCP IQ), layouts, plots and measurements, DSP plots, Python use, extending, performance |
| [Examples](https://anonoei.github.io/pyspecan/examples/) | runnable, self-checking scripts ([examples/](https://github.com/Anonoei/pyspecan/tree/main/examples)) |
| [API](https://anonoei.github.io/pyspecan/api/) | every package; the data path is `pyspecan`, how plots work `pyspecan.plots` |
| [Contributing](https://anonoei.github.io/pyspecan/contributing/) | setup, tests, CI, conventions, releases |

## License
Copyright (C) 2025-2026 Anonoei

pyspecan is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License
as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
It is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See [LICENSE](LICENSE) for the full text.
