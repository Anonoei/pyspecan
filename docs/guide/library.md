# Using pyspecan from Python

There are two ways in: launch a view as the command line would, or run the plots yourself and read their frames.

## Launch a view

`SpecAn(view, sink, layout=None, **options)` takes the command line options by their dest (`python -m pyspecan -v
<view> -s <sink> --help` lists them; `-fs` is `Fs`, `-f` is `path`, `--plot` items are `layout_items`), gives each
part (model, view, plots) only its own, and returns when the view closes. `layout` is a `LayoutSpec` or the path of a
JSON layout.

```python
--8<-- "examples/launch.py"
```

## The plots without a view

A view is only a way of drawing frames. The model reads a block, the `Source` announces it (`tick`), and the
`PlotSet` renders every plot into a `Frame`: traces, images, marker tables, readouts. The quickstart does it for a
file on disk and reads the PSD's marker table:

```python
--8<-- "examples/quickstart.py"
```

- `GetModel(Sink.FILE)` (or `Sink.LIVE`, `Sink.TCPIQ`) takes the same options as the command line's sink and model
  groups. Anything with the model's `samples`, `get_fs`, `get_cf`, `get_nfft` and `get_overlap` can feed a `Source`
  too: [extending](extending.md) and [DSP plots](dsp.md#from-python) feed blocks held in memory.
- `source.tick(contiguous)`: pass the sink's `contiguous`, so a block after lost samples starts the frame streams
  over instead of joining samples that do not follow each other. `source.reset()` after seeking.
- `PlotSet.update()` returns `{plot id: Frame}` for the plots that rendered this block (a plot may skip blocks:
  "Update every", or nothing to draw yet). `plots.get(pid)` is the plot itself; its settings read as attributes.
- `pyspecan.plots.export.FORMATS` turns a frame into CSV (`csv`, `table`) or JSON (`json`).

The pieces are described in [`pyspecan`](../api/pyspecan.md) (the data path) and [`pyspecan.plots`](../api/plots.md).
