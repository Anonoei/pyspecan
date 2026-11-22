# Contributing

How pyspecan is built and how to add to it. The data path and the package map are [`pyspecan`](api/pyspecan.md); how
plots work is [`pyspecan.plots`](api/plots.md). Read them before adding a plot.

## Where documentation goes

| Kind | Home |
|---|---|
| What a package or module is and why (data path, rules, formats) | its docstring: the API pages render it |
| How to use pyspecan for a task | a guide in `docs/guide/`, embedding a script from `examples/` with `--8<-- "examples/<name>.py"` |
| A runnable, self-checking demonstration | `examples/<name>.py`, run by `tests/test_examples.py` |
| What agents need first | `AGENTS.md`; `llms.txt` / `llms-full.txt` are generated from it and the docstrings |
| Screenshots | `media/`, made by `python dev/screenshots.py`, shown in README.md and the [gallery](gallery.md) |

Python blocks in README.md and `docs/` run in `tests/test_docs.py` unless they hold `# docs: skip`. `python
tools/builder.py -d` builds the site with `--strict`, so a broken snippet path or docstring cross-reference fails the
build.

## Setup and workflow

```
git clone https://github.com/Anonoei/pyspecan && cd pyspecan
python tools/builder.py -s        # pip install -e ".[dev]"
python tools/builder.py -t        # pytest
python -m playwright install chromium   # once: the browser tests (tests/test_web_*.py) skip without it
```

`tools/builder.py -h` lists the rest: `-d` docs (API pages and llms files by `tools/gen_docs.py`, then `zensical
build` into `site/`; `zensical serve` to preview), `-b` sdist and wheel (then `twine check`), `-l` local install,
`-v M|m|p` version bump and `-u` upload (both dry runs without `-r`; upload goes to TestPyPI without it).

`pyproject.toml` is the only place that names a dependency, CI included: `dependencies` (numpy, pysdrlib), extras
`tk` (matplotlib), `web` (fastapi, uvicorn, jinja2, websockets), `dsp` (rpps), `test` (pytest, httpx, playwright,
pysdrlib's remote), `docs` (zensical, mkdocstrings-python), `dev` (all of them plus twine, build, bumpver). It also
holds the ruff rules and `[tool.bumpver]`.

Branch from `dev`, merge back into it; `main` is released.

## Repository layout

| Path | What |
|---|---|
| `src/pyspecan/` | the package; each package's `__init__.py` docstring is its documentation |
| `src/pyspecan/view/WEB/static/`, `templates/` | the web page: `app.js` draws frames on canvases |
| `src/build.spec` | the pyinstaller spec of the standalone executable |
| `examples/` | one self-checking script per recommended usage; the guides embed them |
| `tests/` | the suite: `test_plots.py`, `test_measure.py`, `test_dsp.py`, `test_layout.py`, the views (`test_tk.py`, `test_web_*.py`, `test_controller.py`), `test_examples.py`, `test_docs.py` |
| `dev/` | `benchmark.py` (cost of each plot), `screenshots.py` (`media/`), `demo.py` (their synthetic capture), launchers |
| `tools/` | `builder.py` (setup, tests, docs, release), `gen_docs.py` (API pages, llms files) |
| `docs/` | the site: guides, gallery, examples index, this page; `docs/api/` and `docs/llms*.txt` are generated |
| `media/` | screenshots |

## Adding things

- **A plot**: a `Plot` subclass with `@plot("Name")` in `src/pyspecan/plots/`, imported in `plots/__init__.py`;
  `ABOUT` with its cost from `python dev/benchmark.py --plots <name>`. See [Extending](guide/extending.md).
- **A marker kind**: a `MarkerKind` subclass with `@marker_kind("name")` in `plots/markers.py`.
- **A DSP plot**: in `plots/dsp/`, on `common.DSPPlot` and the shared `Analyzer`; rpps imported inside the call.
- **Measurement math**: `pyspecan.measure`, numpy only, tested in `tests/test_measure.py`.
- **A command line option**: in the layer it belongs to (`pyspecan.arguments`: model, ui or plots), which is the only
  one that receives it.
- **A sink**: a `Sink` subclass in `model/sink/` with its `args_*`, registered in `model/model.py`, with a panel in
  each view's controller.

## Testing

```
python -m pytest -q                       # everything; the browser tests need playwright's chromium
xvfb-run -a python -m pytest -q           # Linux without a display: test_tk needs one
PYSPECAN_NO_RPPS=1 python -m pytest -q    # without the DSP plots: everything else must work the same
ruff check src tests dev tools examples   # the rules are in pyproject.toml
```

Run the suite both ways when touching plots. Without playwright and a chromium the browser tests skip, so check they
ran.

## CI and releases

| Workflow | When | Does |
|---|---|---|
| `tests.yml` | push to `main` / `dev`, pull requests | the suite on Python 3.12 and 3.13, Ubuntu and Windows; without rpps; ruff; sdist → wheel in a clean venv (with the web assets); the docs build |
| `deploy-docs.yml` | push to `main` | `python tools/builder.py -d` (Zensical) to GitHub Pages |
| `python-publish.yml` | a GitHub release | builds, checks the tag against the version, publishes to PyPI |
| `deploy-executable.yml` | a GitHub release | the pyinstaller executable for Linux and Windows, attached to the release |

To release: `python tools/builder.py -v p` (or `m`, `M`) previews the bump, `-r` makes it (edits `pyproject.toml` and
`src/pyspecan/__init__.py`, commits and tags); merge to `main`; publish a GitHub release tagged exactly `v<version>`.

The standalone executable builds locally with `pip install ".[tk]" pyinstaller`, then
`pyinstaller --distpath dist --workpath build src/build.spec` and `./dist/pyspecan`.

## Conventions

- **Plots never touch a toolkit:** they return frames; views only draw frames. A plot that needs a new kind of drawing
  adds it to `pyspecan.plots.frame` and to every view.
- **Each layer gets only its own options** (`pyspecan.arguments`).
- **rpps is optional:** imported only inside `plots/dsp/` calls; everything else works with `PYSPECAN_NO_RPPS=1`.
- **I/O through pysdrlib:** file formats, radios, servers and TCP IQ are pysdrlib's; fix them there, not here.
- **No aliases:** a rename or move drops the old name and fixes the callers.
- **Failures are never silent:** a view shows an error in its status line, and it is printed (the logger is off by
  default).
- **Docs live with what they describe:** concepts in the package / module docstring, usage in a guide that embeds an
  example script.
