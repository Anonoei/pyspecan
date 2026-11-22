# Examples

Each script in [examples/](https://github.com/Anonoei/pyspecan/tree/main/examples) shows the way pyspecan recommends
doing one thing, and checks that it worked. Run them from the repository root (`python examples/<name>.py`). They make
their own signals and need nothing else (dsp.py needs rpps, `pip install pyspecan[dsp]`); `tests/test_examples.py`
runs them, and the guides show them in full.

| Script | Shows | In |
| --- | --- | --- |
| quickstart.py | A capture on disk, read block by block, a PSD with a peak marker, its marker table | [Using pyspecan from Python](guide/library.md#the-plots-without-a-view) |
| launch.py | A view (web, tk, console) launched from Python, as the command line would | [Using pyspecan from Python](guide/library.md#launch-a-view) |
| layout.py, layout.json | A layout from JSON and from `--plot` / `--row` items, applied and saved back | [Layouts](guide/layouts.md#from-python) |
| extension.py | A plot and a marker kind of your own, rendered on a block held in memory | [Extending](guide/extending.md#a-plot-and-a-marker-kind) |
| dsp.py | The `signals` marker finding two signals, the Constellation locking to the QPSK one | [DSP plots](guide/dsp.md#from-python) |

The developer tools in [dev/](https://github.com/Anonoei/pyspecan/tree/main/dev) are worth reading too:
`benchmark.py` ([Performance](guide/performance.md)) and `screenshots.py` ([Gallery](gallery.md)) build layouts and
drive every view.
