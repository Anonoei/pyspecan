"""Profile the plots: how long each takes to render a block, measured in PSDs (a PSD on the same blocks is 1.0)

    python dev/profile_plots.py                            # every plot, the analyzer's defaults (1 MS/s, 1024 FFT, 50 ms blocks)
    python dev/profile_plots.py --nfft 4096 --sweep 20     # other FFT size / block length
    python dev/profile_plots.py --plots psd,scope,scalogram
    python dev/profile_plots.py --markers                  # also what each marker kind adds to a PSD
    python dev/profile_plots.py --set "Scope trig_mode=roll" --set "PSD points=0"
    python dev/profile_plots.py --json profile.json        # the numbers, to compare runs

Each plot runs alone on its own source, so it pays for everything it needs (in a layout, plots share the source's
FFT frames and the DSP plots one signal search and lock). The first blocks are a warm-up (caches, the DSP plots' full
search), timed but left out of the median; "first" shows the first one. "realtime" is the median against the block's
own duration: over 100% the plot can not keep up with live samples at this rate on its own.

The blocks come from dev/demo.py's synthetic capture (QPSK, FM, tones, a burst, a chirp), the DSP plots analyse the
QPSK at 150 kHz.
"""
import argparse
import json
import pathlib
import shlex
import statistics
import sys
import time

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from demo import capture # noqa: E402

REFERENCE = "PSD"
DSP_GLOBALS = {"dsp_freq": "150k", "dsp_bw": "60k"}

class Model:
    """The parts of a model plots read, fed one block at a time"""
    def __init__(self, fs: float, nfft: int, overlap: float):
        from pyspecan.obj import Frequency
        self._fs, self._cf = Frequency.get(fs), Frequency.get(0)
        self.nfft, self.overlap = nfft, overlap
        self.samples = np.zeros(0, dtype=np.complex64)
    def get_fs(self): return self._fs
    def get_cf(self): return self._cf
    def get_nfft(self): return self.nfft
    def get_overlap(self): return self.overlap

def run(name: str, settings: dict, a, data: np.ndarray, markers: tuple = ()) -> dict:
    """Render `name` on blocks of `data`, alone on a fresh source: {"times": [s per block, warm-up first]}"""
    from pyspecan.plots import PLOTS, Source
    from pyspecan.plots.base import default_globals
    model = Model(a.fs, a.nfft, a.overlap)
    src = Source(model)
    plot = PLOTS.get(name)(src, globals=default_globals(**DSP_GLOBALS), **settings)
    for kind in markers:
        plot.markers.add(kind)
    block = a.block
    times = []
    for i in range(a.warmup + a.blocks):
        model.samples = data[i * block:(i + 1) * block]
        src.tick()
        t0 = time.perf_counter()
        plot.update()
        times.append(time.perf_counter() - t0)
    return {"times": times}

def stats(times: list, warmup: int) -> dict:
    t = times[warmup:] or times
    return {"median": statistics.median(t), "p90": float(np.percentile(t, 90)), "mean": statistics.mean(t), "first": times[0]}

def parse_sets(items: list) -> dict:
    """["Scope trig_mode=roll", ...] -> {"Scope": {"trig_mode": "roll"}}"""
    from pyspecan.plots import layout
    out: dict = {}
    for item in items:
        name, *kvs = shlex.split(item)
        out.setdefault(layout.resolve_type(name), {}).update(dict(kv.split("=", 1) for kv in kvs))
    return out

def table(rows: list, headers: list) -> str:
    w = [max(len(str(r[k])) for r in [headers, *rows]) for k in range(len(headers))]
    line = lambda r: "  ".join(str(c).rjust(w[k]) if k else str(c).ljust(w[k]) for k, c in enumerate(r))
    return "\n".join([line(headers), line(["-" * x for x in w]), *map(line, rows)])

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--fs", type=float, default=1e6, help="sample rate (S/s)")
    ap.add_argument("--nfft", type=int, default=1024, help="the analyzer's FFT size")
    ap.add_argument("--overlap", type=float, default=0.6, help="realtime frame overlap")
    ap.add_argument("--sweep", type=float, default=50.0, help="block length (ms), the analyzer's sweep time")
    ap.add_argument("--blocks", type=int, default=20, help="blocks timed per plot")
    ap.add_argument("--warmup", type=int, default=3, help="blocks rendered first and not counted")
    ap.add_argument("--plots", default="", help="comma separated plot names (default: all), the PSD is always run")
    ap.add_argument("--set", action="append", default=[], metavar="'PLOT key=value ...'", help="settings for a plot")
    ap.add_argument("--markers", action="store_true", help="also time each marker kind on a PSD")
    ap.add_argument("--sort", choices=("cost", "name"), default="cost")
    ap.add_argument("--json", default=None, metavar="FILE", help="write the numbers here")
    a = ap.parse_args()
    from pyspecan.plots import PLOTS, MARKER_KINDS, layout
    a.block = int(round(a.fs * a.sweep / 1000))
    data = capture((a.warmup + a.blocks) * a.block + 1)
    sets = parse_sets(a.set)
    names = [layout.resolve_type(n) for n in a.plots.split(",") if n.strip()] if a.plots else list(PLOTS.names())
    if REFERENCE not in names:
        names.insert(0, REFERENCE)
    block_s = a.block / a.fs

    print(f"{a.fs / 1e6:g} MS/s, FFT {a.nfft}, blocks of {a.block} samples ({a.sweep:g} ms), "
          f"{a.blocks} timed after {a.warmup} warm-up", file=sys.stderr)
    results = {}
    for name in names:
        print(f"  {name}...", end="", flush=True, file=sys.stderr)
        try:
            r = stats(run(name, sets.get(name, {}), a, data)["times"], a.warmup)
        except Exception as e: # one plot failing (rpps missing...) does not stop the others
            r = {"error": f"{type(e).__name__}: {e}"}
        results[name] = r
        print(f" {r['median'] * 1e3:.2f} ms" if "median" in r else f" {r['error']}", file=sys.stderr)
    ref = results[REFERENCE]["median"]

    rows = []
    for name, r in results.items():
        if "error" in r:
            rows.append([name, "-", "-", "-", "-", "-", r["error"]])
            continue
        rows.append([name, f"{r['median'] / ref:.2f}", f"{r['median'] * 1e3:.2f}", f"{r['p90'] * 1e3:.2f}",
                     f"{r['first'] * 1e3:.1f}", f"{r['median'] / block_s * 100:.1f}%", ",".join(sorted(PLOTS.get(name).FEATURES))])
    key = (lambda r: -float(r[1]) if r[1] != "-" else 1e9) if a.sort == "cost" else (lambda r: r[0].lower())
    rows.sort(key=key)
    print(f"\nPSD reference: {ref * 1e3:.2f} ms a block\n")
    print(table(rows, ["Plot", "x PSD", "median ms", "p90 ms", "first ms", "realtime", "draws"]))

    marks = {}
    if a.markers:
        print("\nMarkers: what each adds to a PSD\n", file=sys.stderr)
        mrows = []
        for kind in MARKER_KINDS.names():
            try:
                m = stats(run(REFERENCE, sets.get(REFERENCE, {}), a, data, (kind,))["times"], a.warmup)
                extra = m["median"] - ref
                marks[kind] = {**m, "extra": extra}
                mrows.append([kind, f"{extra / ref:+.2f}", f"{extra * 1e3:+.2f}", f"{m['median'] * 1e3:.2f}"])
            except Exception as e:
                marks[kind] = {"error": f"{type(e).__name__}: {e}"}
                mrows.append([kind, "-", "-", marks[kind]["error"]])
        mrows.sort(key=lambda r: -float(r[1]) if r[1] != "-" else 1e9)
        print(table(mrows, ["Marker", "+ x PSD", "+ ms", "PSD with it, ms"]))

    if a.json:
        out = {"config": {"fs": a.fs, "nfft": a.nfft, "overlap": a.overlap, "block": a.block, "blocks": a.blocks, "warmup": a.warmup},
               "reference": {"plot": REFERENCE, "median": ref}, "plots": results, "markers": marks}
        pathlib.Path(a.json).write_text(json.dumps(out, indent=2))
        print(f"\nwrote {a.json}", file=sys.stderr)

if __name__ == "__main__":
    main()
